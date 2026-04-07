import json
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import redis
from kafka import KafkaProducer
from redis.exceptions import RedisError

from config import settings


redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

# Redis Key 协议要集中管理，而不是散落在路由和消费者里：
# 秒杀链路天生跨“请求入口、异步消费者、补偿逻辑、排障脚本”多个位置。
# 一旦 Key 规则四处分叉，后面出现库存对不上、订单状态查不到时，排查成本会比编码成本高得多。
FLASH_SALE_STOCK_PREFIX = "flashsale:stock:"
FLASH_SALE_USER_ORDER_PREFIX = "flashsale:user-order:"
FLASH_SALE_ORDER_STATUS_PREFIX = "flashsale:order-status:"

# 这段 Lua 脚本是秒杀入口的并发闸门。
# 为什么一定要放到 Redis 原子执行，而不是 Python 里“先查库存、再判断重复、最后扣减”：
# 因为秒杀场景真正危险的不是单个请求逻辑复杂，而是数百上千个请求同时命中同一商品。
# 如果三个动作拆成多次网络往返，中间任何一步都可能被并发插队，最后出现超卖或重复下单。
FLASH_SALE_RESERVE_SCRIPT = """
local stock_key = KEYS[1]
local user_order_key = KEYS[2]
local order_status_key = KEYS[3]

local order_id = ARGV[1]
local product_id = ARGV[2]
local user_id = ARGV[3]
local quantity = tonumber(ARGV[4])
local order_status_ttl = tonumber(ARGV[5])
local user_mark_ttl = tonumber(ARGV[6])

local existing_order_id = redis.call('GET', user_order_key)
if existing_order_id then
    return {2, existing_order_id}
end

local current_stock = redis.call('GET', stock_key)
if not current_stock then
    return {-1, 'STOCK_NOT_PRELOADED'}
end

current_stock = tonumber(current_stock)
if current_stock < quantity then
    return {0, tostring(current_stock)}
end

redis.call('DECRBY', stock_key, quantity)
redis.call('SET', user_order_key, order_id, 'EX', user_mark_ttl)
redis.call(
    'HSET',
    order_status_key,
    'order_id', order_id,
    'product_id', product_id,
    'user_id', user_id,
    'quantity', quantity,
    'status', 'QUEUED',
    'message', '秒杀请求已进入 Kafka 队列，等待异步创建订单',
    'create_time', ARGV[7]
)
redis.call('EXPIRE', order_status_key, order_status_ttl)
return {1, order_id}
"""

_producer_lock = threading.Lock()
_producer: Optional[KafkaProducer] = None


class SnowflakeIdGenerator:
    # 这里使用雪花算法而不是数据库自增 ID：
    # 1. 订单号必须在“进入队列之前”就生成出来，方便用户立即拿到查询凭证；
    # 2. 自增 ID 会把强依赖前置到数据库，反而削弱了 MQ 削峰的价值；
    # 3. 雪花 ID 基本有序，后续按时间排查日志、按范围分片都会更自然。
    CUSTOM_EPOCH_MS = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)

    def __init__(self, worker_id: int):
        self.worker_id = worker_id & 0x3FF
        self.sequence = 0
        self.last_timestamp = -1
        self._lock = threading.Lock()

    def _current_timestamp_ms(self) -> int:
        return int(time.time() * 1000)

    def _wait_until_next_millisecond(self, last_timestamp: int) -> int:
        timestamp = self._current_timestamp_ms()
        while timestamp <= last_timestamp:
            time.sleep(0.001)
            timestamp = self._current_timestamp_ms()
        return timestamp

    def next_id(self) -> str:
        with self._lock:
            timestamp = self._current_timestamp_ms()
            if timestamp < self.last_timestamp:
                # WARNING:
                # 时钟回拨在分布式 ID 里属于高危事件。
                # 这里选择“短暂等待到安全时间点”而不是直接继续生成，
                # 是因为继续生成会把“偶发的机器时间漂移”升级成“订单号冲突或乱序”。
                timestamp = self._wait_until_next_millisecond(self.last_timestamp)

            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & 0xFFF
                if self.sequence == 0:
                    timestamp = self._wait_until_next_millisecond(self.last_timestamp)
            else:
                self.sequence = 0

            self.last_timestamp = timestamp
            snowflake_id = (
                ((timestamp - self.CUSTOM_EPOCH_MS) << 22)
                | (self.worker_id << 12)
                | self.sequence
            )
            return str(snowflake_id)


order_id_generator = SnowflakeIdGenerator(settings.order_id_worker_id)


def flash_sale_stock_key(product_id: str) -> str:
    return f"{FLASH_SALE_STOCK_PREFIX}{product_id}"


def flash_sale_user_order_key(product_id: str, user_id: str) -> str:
    return f"{FLASH_SALE_USER_ORDER_PREFIX}{product_id}:{user_id}"


def flash_sale_order_status_key(order_id: str) -> str:
    return f"{FLASH_SALE_ORDER_STATUS_PREFIX}{order_id}"


def generate_order_id() -> str:
    return order_id_generator.next_id()


def get_kafka_producer() -> KafkaProducer:
    global _producer
    if _producer is not None:
        return _producer

    with _producer_lock:
        if _producer is None:
            _producer = KafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_server_list,
                value_serializer=lambda payload: json.dumps(payload).encode("utf-8"),
                key_serializer=lambda key: key.encode("utf-8"),
                acks="all",
                retries=3,
            )
    return _producer


def close_kafka_producer() -> None:
    global _producer
    with _producer_lock:
        if _producer is not None:
            _producer.close()
            _producer = None


def try_reserve_flash_sale_stock(product_id: str, user_id: str, quantity: int, order_id: str) -> tuple[str, Optional[str]]:
    try:
        result = redis_client.eval(
            FLASH_SALE_RESERVE_SCRIPT,
            3,
            flash_sale_stock_key(product_id),
            flash_sale_user_order_key(product_id, user_id),
            flash_sale_order_status_key(order_id),
            order_id,
            product_id,
            user_id,
            quantity,
            settings.flash_sale_order_status_ttl_seconds,
            settings.flash_sale_user_mark_ttl_seconds,
            datetime.now(timezone.utc).isoformat(),
        )
    except RedisError as exc:
        print(f"Redis 预扣库存失败: {exc}")
        return "REDIS_ERROR", None

    status_code = int(result[0])
    detail = str(result[1]) if len(result) > 1 else None

    if status_code == 1:
        return "SUCCESS", detail
    if status_code == 2:
        return "DUPLICATE_ORDER", detail
    if status_code == 0:
        return "OUT_OF_STOCK", detail
    if status_code == -1:
        return "STOCK_NOT_PRELOADED", detail
    return "UNKNOWN_ERROR", detail


def update_async_order_status(order_id: str, status: str, message: str, extra: Optional[dict] = None) -> None:
    order_status_key = flash_sale_order_status_key(order_id)
    payload = {
        "status": status,
        "message": message,
    }
    if extra:
        payload.update(extra)

    try:
        pipeline = redis_client.pipeline()
        pipeline.hset(order_status_key, mapping=payload)
        pipeline.expire(order_status_key, settings.flash_sale_order_status_ttl_seconds)
        pipeline.execute()
    except RedisError as exc:
        # WARNING:
        # 订单状态缓存主要用于“异步阶段的可观测性增强”，不是最终事实源。
        # 这里失败不应该影响真正的订单创建，否则会把可观测性问题反过来变成业务失败。
        print(f"Redis 更新异步订单状态失败: {exc}")


def get_async_order_status(order_id: str) -> Optional[dict]:
    try:
        payload = redis_client.hgetall(flash_sale_order_status_key(order_id))
    except RedisError as exc:
        print(f"Redis 查询异步订单状态失败: {exc}")
        return None
    return payload or None


def compensate_flash_sale_reservation(
    product_id: str,
    user_id: str,
    quantity: int,
    order_id: str,
    message: str,
    fallback_order_id: Optional[str] = None,
) -> None:
    # 为什么补偿里要同时处理库存和用户幂等标记：
    # 只回库存不清购买标记，用户会被永久误判成“已经抢到过”；
    # 只清购买标记不回库存，又会把真实可售库存越扣越少。
    user_order_key = flash_sale_user_order_key(product_id, user_id)
    try:
        pipeline = redis_client.pipeline()
        pipeline.incrby(flash_sale_stock_key(product_id), quantity)
        if fallback_order_id:
            pipeline.set(user_order_key, fallback_order_id, ex=settings.flash_sale_user_mark_ttl_seconds)
        else:
            pipeline.delete(user_order_key)
        pipeline.hset(
            flash_sale_order_status_key(order_id),
            mapping={
                "order_id": order_id,
                "product_id": product_id,
                "user_id": user_id,
                "quantity": quantity,
                "status": "FAILED",
                "message": message,
            },
        )
        pipeline.expire(flash_sale_order_status_key(order_id), settings.flash_sale_order_status_ttl_seconds)
        pipeline.execute()
    except RedisError as exc:
        print(f"Redis 秒杀补偿失败: {exc}")
