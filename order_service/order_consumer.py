import threading
import time
from decimal import Decimal
from typing import Optional

import httpx
from kafka import KafkaConsumer
from kafka.errors import KafkaError, NoBrokersAvailable
from sqlalchemy.exc import IntegrityError

import database
import models
import schemas
from config import settings
from flash_sale import (
    compensate_flash_sale_reservation,
    update_async_order_status,
)


class RetryableFlashSaleError(Exception):
    pass


class NonRetryableFlashSaleError(Exception):
    pass


class FlashSaleOrderConsumer:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="flash-sale-order-consumer")

    def start(self) -> None:
        if self._thread.is_alive():
            return
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=10)

    def _create_consumer(self) -> KafkaConsumer:
        return KafkaConsumer(
            settings.kafka_flash_sale_topic,
            bootstrap_servers=settings.kafka_bootstrap_server_list,
            group_id=settings.kafka_consumer_group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            value_deserializer=lambda payload: schemas.FlashSaleOrderEvent.model_validate_json(payload.decode("utf-8")),
        )

    def _run(self) -> None:
        # WARNING:
        # 这里把消费者内嵌在 API 服务进程里，是为了让课程作业能通过一个容器把整条链路跑通。
        # 真正线上通常会把 consumer 单独拆成 worker 进程，避免 Web 容器横向扩容时带来消费实例数失控。
        while not self._stop_event.is_set():
            consumer: Optional[KafkaConsumer] = None
            try:
                consumer = self._create_consumer()
                print("[FLASH SALE] Kafka 消费者已启动，开始监听秒杀订单消息")
                while not self._stop_event.is_set():
                    records_map = consumer.poll(timeout_ms=1000, max_records=10)
                    if not records_map:
                        continue

                    for _, records in records_map.items():
                        for record in records:
                            should_commit = self._handle_event(record.value)
                            if should_commit:
                                consumer.commit()
            except NoBrokersAvailable as exc:
                print(f"[FLASH SALE] Kafka 尚未就绪，稍后重试: {exc}")
                self._stop_event.wait(settings.flash_sale_consumer_retry_interval_seconds)
            except KafkaError as exc:
                print(f"[FLASH SALE] Kafka 消费异常，稍后重试: {exc}")
                self._stop_event.wait(settings.flash_sale_consumer_retry_interval_seconds)
            except Exception as exc:
                print(f"[FLASH SALE] 秒杀消费者异常，稍后重试: {exc}")
                self._stop_event.wait(settings.flash_sale_consumer_retry_interval_seconds)
            finally:
                if consumer is not None:
                    consumer.close()

    def _handle_event(self, event: schemas.FlashSaleOrderEvent) -> bool:
        last_error = "未知异常"
        for attempt in range(1, settings.flash_sale_consumer_max_retries + 1):
            try:
                self._process_event(event)
                return True
            except NonRetryableFlashSaleError as exc:
                last_error = str(exc)
                break
            except RetryableFlashSaleError as exc:
                last_error = str(exc)
                print(
                    f"[FLASH SALE] 第 {attempt} 次消费失败，将进行重试: "
                    f"order_id={event.order_id}, reason={last_error}"
                )
                time.sleep(settings.flash_sale_consumer_retry_interval_seconds)
            except Exception as exc:
                last_error = f"未捕获异常: {exc}"
                print(f"[FLASH SALE] 消费异常: order_id={event.order_id}, reason={last_error}")
                time.sleep(settings.flash_sale_consumer_retry_interval_seconds)

        self._mark_event_failed(event, last_error)
        return True

    def _process_event(self, event: schemas.FlashSaleOrderEvent) -> None:
        existing_order = self._get_order_by_id(event.order_id)
        if existing_order and existing_order.status in {"PENDING_PAYMENT", "PAID", "CANCELLED"}:
            update_async_order_status(
                event.order_id,
                existing_order.status,
                "订单已经创建完成，无需重复消费",
                {
                    "order_id": existing_order.id,
                    "product_id": existing_order.product_id,
                    "user_id": existing_order.user_id,
                    "quantity": existing_order.quantity,
                    "amount": float(existing_order.amount),
                },
            )
            return

        if existing_order and existing_order.status == "FAILED":
            update_async_order_status(
                event.order_id,
                "FAILED",
                existing_order.failure_reason or "订单处理失败",
                {
                    "order_id": existing_order.id,
                    "product_id": existing_order.product_id,
                    "user_id": existing_order.user_id,
                    "quantity": existing_order.quantity,
                },
            )
            return

        duplicate_order = self._find_duplicate_user_order(event)
        if duplicate_order and duplicate_order.id != event.order_id:
            compensate_flash_sale_reservation(
                event.product_id,
                event.user_id,
                event.quantity,
                event.order_id,
                f"检测到同一用户已存在秒杀订单 {duplicate_order.id}，已拦截重复下单",
                fallback_order_id=duplicate_order.id,
            )
            return

        product_data = self._fetch_product_detail(event.product_id)
        order = self._ensure_processing_order(event, Decimal(str(product_data["flash_price"])))

        self._commit_inventory(event)
        self._mark_order_success(order.id)
        update_async_order_status(
            order.id,
            "PENDING_PAYMENT",
            "订单创建成功，等待支付",
            {
                "order_id": order.id,
                "product_id": order.product_id,
                "user_id": order.user_id,
                "quantity": order.quantity,
                "amount": float(order.amount),
            },
        )

    def _fetch_product_detail(self, product_id: str) -> dict:
        try:
            with httpx.Client(timeout=settings.internal_service_timeout_seconds) as client:
                response = client.get(f"{settings.product_service_url}/api/products/{product_id}")
        except httpx.HTTPError as exc:
            raise RetryableFlashSaleError(f"调用商品服务失败: {exc}") from exc

        if response.status_code == 404:
            raise NonRetryableFlashSaleError("商品不存在，已终止订单创建")
        if response.status_code != 200:
            raise RetryableFlashSaleError(f"商品服务返回异常状态码: {response.status_code}")

        payload = response.json()
        product_data = payload.get("data")
        if not product_data:
            raise RetryableFlashSaleError("商品服务返回数据为空")
        return product_data

    def _commit_inventory(self, event: schemas.FlashSaleOrderEvent) -> None:
        try:
            with httpx.Client(timeout=settings.internal_service_timeout_seconds) as client:
                response = client.post(
                    f"{settings.inventory_service_url}/api/inventory/{event.product_id}/flash-sale/commit",
                    json={
                        "order_id": event.order_id,
                        "user_id": event.user_id,
                        "quantity": event.quantity,
                    },
                )
        except httpx.HTTPError as exc:
            raise RetryableFlashSaleError(f"调用库存服务失败: {exc}") from exc

        if response.status_code == 409:
            raise NonRetryableFlashSaleError("库存最终扣减失败，数据库状态与缓存预扣出现冲突")
        if response.status_code >= 500:
            raise RetryableFlashSaleError(f"库存服务内部错误: {response.status_code}")
        if response.status_code != 200:
            raise NonRetryableFlashSaleError(f"库存服务拒绝扣减: {response.text}")

    def _ensure_processing_order(self, event: schemas.FlashSaleOrderEvent, amount: Decimal) -> models.Order:
        with database.SessionLocal() as db:
            order = db.query(models.Order).filter(models.Order.id == event.order_id).first()
            if order:
                return order

            order = models.Order(
                id=event.order_id,
                user_id=event.user_id,
                product_id=event.product_id,
                amount=amount,
                quantity=event.quantity,
                status="PROCESSING",
            )
            db.add(order)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                existing = (
                    db.query(models.Order)
                    .filter(
                        models.Order.user_id == event.user_id,
                        models.Order.product_id == event.product_id,
                    )
                    .first()
                )
                if existing:
                    return existing
                raise
            db.refresh(order)
            update_async_order_status(
                order.id,
                "PROCESSING",
                "秒杀请求已被消费者接收，正在创建订单",
                {
                    "order_id": order.id,
                    "product_id": order.product_id,
                    "user_id": order.user_id,
                    "quantity": order.quantity,
                    "amount": float(order.amount),
                },
            )
            return order

    def _mark_order_success(self, order_id: str) -> None:
        with database.SessionLocal() as db:
            order = db.query(models.Order).filter(models.Order.id == order_id).first()
            if not order:
                raise RetryableFlashSaleError("订单记录不存在，无法更新成功状态")
            order.status = "PENDING_PAYMENT"
            order.failure_reason = None
            db.commit()

    def _mark_event_failed(self, event: schemas.FlashSaleOrderEvent, reason: str) -> None:
        with database.SessionLocal() as db:
            order = db.query(models.Order).filter(models.Order.id == event.order_id).first()
            if order:
                order.status = "FAILED"
                order.failure_reason = reason
                db.commit()

        compensate_flash_sale_reservation(
            event.product_id,
            event.user_id,
            event.quantity,
            event.order_id,
            f"订单创建失败，已自动补偿 Redis 库存。原因: {reason}",
        )

    def _get_order_by_id(self, order_id: str) -> Optional[models.Order]:
        with database.SessionLocal() as db:
            return db.query(models.Order).filter(models.Order.id == order_id).first()

    def _find_duplicate_user_order(self, event: schemas.FlashSaleOrderEvent) -> Optional[models.Order]:
        with database.SessionLocal() as db:
            return (
                db.query(models.Order)
                .filter(
                    models.Order.user_id == event.user_id,
                    models.Order.product_id == event.product_id,
                    models.Order.status.in_(["PROCESSING", "PENDING_PAYMENT", "PAID", "CANCELLED"]),
                )
                .first()
            )


consumer_runtime = FlashSaleOrderConsumer()


def start_flash_sale_consumer() -> None:
    consumer_runtime.start()


def stop_flash_sale_consumer() -> None:
    consumer_runtime.stop()
