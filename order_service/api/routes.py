from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from kafka.errors import KafkaError
from sqlalchemy.orm import Session

import database
import models
import schemas
from config import settings
from core.responses import ResponseModel, success
from core.security import get_current_user_id
from flash_sale import (
    compensate_flash_sale_reservation,
    generate_order_id,
    get_async_order_status,
    get_kafka_producer,
    try_reserve_flash_sale_stock,
    update_async_order_status,
)


router = APIRouter(prefix="/api/orders", tags=["Orders"])


async def preload_flash_sale_stock(product_id: str) -> None:
    # 为什么遇到“库存 Key 不存在”时不立刻判定失败：
    # Redis 里的库存本质上是高并发闸门，不是唯一事实源。
    # 在服务冷启动、Redis 重启或管理员刚初始化库存后，缓存可能尚未预热，
    # 这时让订单服务主动触发一次预热，能减少“明明有库存却抢不到”的假失败。
    async with httpx.AsyncClient(timeout=settings.internal_service_timeout_seconds) as client:
        response = await client.post(
            f"{settings.inventory_service_url}/api/inventory/{product_id}/flash-sale/preload"
        )

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="商品库存不存在，暂时无法参与秒杀")
    if response.status_code != 200:
        raise HTTPException(status_code=503, detail="库存服务未就绪，请稍后重试")


def build_order_status_response(order: models.Order) -> schemas.OrderStatusResponse:
    message_map = {
        "PROCESSING": "订单正在异步创建中",
        "PENDING_PAYMENT": "订单创建成功，等待支付",
        "PAID": "订单已支付",
        "CANCELLED": "订单已取消",
        "FAILED": order.failure_reason or "订单创建失败",
    }
    return schemas.OrderStatusResponse(
        order_id=order.id,
        user_id=order.user_id,
        product_id=order.product_id,
        quantity=order.quantity,
        status=order.status,
        message=message_map.get(order.status, "订单状态未知"),
        amount=float(order.amount),
        failure_reason=order.failure_reason,
        create_time=order.create_time,
    )


def build_cached_order_status_response(order_id: str, payload: dict) -> schemas.OrderStatusResponse:
    create_time_text = payload.get("create_time")
    create_time = None
    if create_time_text:
        try:
            create_time = datetime.fromisoformat(create_time_text)
        except ValueError:
            create_time = None

    amount = payload.get("amount")
    return schemas.OrderStatusResponse(
        order_id=order_id,
        user_id=payload.get("user_id", ""),
        product_id=payload.get("product_id", ""),
        quantity=int(payload.get("quantity", 1)),
        status=payload.get("status", "UNKNOWN"),
        message=payload.get("message", "订单状态未知"),
        amount=float(amount) if amount is not None else None,
        failure_reason=payload.get("failure_reason"),
        create_time=create_time,
    )


# ==========================================
# 🛒 1. 秒杀下单入口 (Redis 预扣库存 -> Kafka 异步建单)
# ==========================================
@router.post("", response_model=ResponseModel[schemas.OrderSubmitResponse])
async def create_order(
    order_req: schemas.OrderCreate,
    user_id: str = Depends(get_current_user_id),
):
    # 这里故意不在请求线程里直接查库和写库：
    # 秒杀真正需要优化的是“洪峰瞬间的写放大”。如果入口线程还同步访问商品服务、库存服务、订单库，
    # 那么 Kafka 只是名义上接进来了，系统瓶颈并没有转移。
    order_id = generate_order_id()
    reservation_status, detail = try_reserve_flash_sale_stock(order_req.product_id, user_id, 1, order_id)

    if reservation_status == "STOCK_NOT_PRELOADED":
        await preload_flash_sale_stock(order_req.product_id)
        reservation_status, detail = try_reserve_flash_sale_stock(order_req.product_id, user_id, 1, order_id)

    if reservation_status == "DUPLICATE_ORDER":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"同一用户同一商品只能秒杀一次，已存在订单 {detail}",
        )
    if reservation_status == "OUT_OF_STOCK":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="手慢了，库存不足啦！")
    if reservation_status == "REDIS_ERROR":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="秒杀闸门暂时不可用，请稍后重试")
    if reservation_status != "SUCCESS":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="秒杀请求处理失败")

    event = schemas.FlashSaleOrderEvent(
        order_id=order_id,
        user_id=user_id,
        product_id=order_req.product_id,
        quantity=1,
        enqueue_time=datetime.now(timezone.utc),
    )

    try:
        future = get_kafka_producer().send(
            settings.kafka_flash_sale_topic,
            key=order_id,
            value=event.model_dump(mode="json"),
        )
        # 为什么这里要等待 broker 确认，而不是 fire-and-forget：
        # Redis 预扣库存已经生效了，如果消息根本没进 Kafka 就直接返回成功，后面就会出现“库存少了但订单没了”的假死状态。
        # 因此至少要等到 broker 确认接收成功，入口线程才有资格告诉用户“你已经进入排队”。
        future.get(timeout=settings.internal_service_timeout_seconds)
    except KafkaError as exc:
        compensate_flash_sale_reservation(
            order_req.product_id,
            user_id,
            1,
            order_id,
            f"Kafka 投递失败，已回补库存。原因: {exc}",
        )
        update_async_order_status(order_id, "FAILED", f"Kafka 投递失败: {exc}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="消息队列暂时不可用，请稍后重试")
    except Exception as exc:
        compensate_flash_sale_reservation(
            order_req.product_id,
            user_id,
            1,
            order_id,
            f"秒杀消息发送异常，已回补库存。原因: {exc}",
        )
        update_async_order_status(order_id, "FAILED", f"秒杀消息发送异常: {exc}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="秒杀请求入队失败，请稍后重试")

    return success(
        data=schemas.OrderSubmitResponse(
            order_id=order_id,
            status="QUEUED",
            message="秒杀请求已入队，系统正在异步创建订单，请稍后查询订单状态",
        ),
        message="秒杀请求已成功进入队列",
    )


# ==========================================
# 👤 2. 按用户 ID 查询订单列表
# ==========================================
@router.get("/user/{target_user_id}", response_model=ResponseModel[list[schemas.OrderResponse]])
def get_orders_by_user(
    target_user_id: str,
    db: Session = Depends(database.get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    if target_user_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能查询别人的订单列表")

    orders = (
        db.query(models.Order)
        .filter(models.Order.user_id == target_user_id)
        .order_by(models.Order.create_time.desc())
        .all()
    )
    return success(data=orders, message="查询用户订单成功")


# ==========================================
# 🔎 3. 按订单 ID 查询订单
# ==========================================
@router.get("/{order_id}", response_model=ResponseModel[schemas.OrderStatusResponse])
def get_order(
    order_id: str,
    db: Session = Depends(database.get_db),
    user_id: str = Depends(get_current_user_id),
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order:
        if order.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能查询别人的订单")
        return success(data=build_order_status_response(order), message="查询订单成功")

    # 为什么 DB 没查到还要继续查 Redis：
    # 因为 MQ 异步架构下，订单“已受理”到“已落库”之间天然存在一个时间窗口。
    # 如果这时直接返回 404，用户会误以为请求丢了；查一下状态缓存，可以把系统正在排队中的真实情况反馈出去。
    cached_status = get_async_order_status(order_id)
    if cached_status:
        if cached_status.get("user_id") != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能查询别人的订单")
        return success(
            data=build_cached_order_status_response(order_id, cached_status),
            message="查询异步订单状态成功",
        )

    raise HTTPException(status_code=404, detail="订单不存在")


# ==========================================
# 💰 4. 模拟付款成功
# ==========================================
@router.post("/{order_id}/pay", response_model=ResponseModel[dict])
def pay_order(
    order_id: str,
    db: Session = Depends(database.get_db),
    user_id: str = Depends(get_current_user_id),
):
    order = db.query(models.Order).filter(models.Order.id == order_id, models.Order.user_id == user_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status != "PENDING_PAYMENT":
        raise HTTPException(status_code=400, detail="只有待支付订单才能付款")

    order.status = "PAID"
    order.failure_reason = None
    db.commit()
    update_async_order_status(
        order_id,
        "PAID",
        "订单已支付",
        {
            "order_id": order.id,
            "product_id": order.product_id,
            "user_id": order.user_id,
            "quantity": order.quantity,
            "amount": float(order.amount),
        },
    )
    return success(data={"order_id": order_id, "status": "PAID"}, message="付款成功！老板大气！")


# ==========================================
# ❌ 5. 模拟取消订单
# ==========================================
@router.post("/{order_id}/cancel", response_model=ResponseModel[dict])
async def cancel_order(
    order_id: str,
    db: Session = Depends(database.get_db),
    user_id: str = Depends(get_current_user_id),
):
    order = db.query(models.Order).filter(models.Order.id == order_id, models.Order.user_id == user_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status != "PENDING_PAYMENT":
        raise HTTPException(status_code=400, detail="只有待支付订单才能取消")

    async with httpx.AsyncClient(timeout=settings.internal_service_timeout_seconds) as client:
        response = await client.post(
            f"{settings.inventory_service_url}/api/inventory/{order.product_id}/flash-sale/restore",
            json={
                "order_id": order.id,
                "user_id": order.user_id,
                "quantity": order.quantity,
            },
        )

    if response.status_code != 200:
        raise HTTPException(status_code=500, detail="库存回补失败，订单取消中止")

    order.status = "CANCELLED"
    db.commit()
    update_async_order_status(
        order_id,
        "CANCELLED",
        "订单已取消，库存已回补",
        {
            "order_id": order.id,
            "product_id": order.product_id,
            "user_id": order.user_id,
            "quantity": order.quantity,
            "amount": float(order.amount),
        },
    )
    return success(data={"order_id": order_id, "status": "CANCELLED"}, message="订单已取消，库存已回补。")
