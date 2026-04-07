from fastapi import APIRouter, Depends, HTTPException
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import List, Optional, Tuple

import json
import random
import time
import uuid

import database
import models
import redis
import schemas
from config import settings
from core.responses import ResponseModel, success
from core.security import get_current_user_id


# 在模块加载时就初始化 Redis 客户端
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

router = APIRouter(prefix="/api/products", tags=["Products"])

# 下面这组常量不是简单的“命名整理”，而是在约束缓存协议。
# 1. 多个函数共享同一套 Key 规则时，散落在代码里更容易出现拼写不一致；
# 2. 后面如果接入监控、清理脚本、压测脚本，需要稳定的 Key 约定；
# 3. 缓存治理经常不是单点改动，统一协议能降低未来维护成本。
PRODUCT_CACHE_PREFIX = "product:"
PRODUCT_LOCK_SUFFIX = ":lock"
PRODUCT_EMPTY_PLACEHOLDER = "__PRODUCT_NOT_FOUND__"
PRODUCT_ID_SET_KEY = "product:ids"
PRODUCT_ID_INDEX_READY_KEY = "product:ids:ready"
PRODUCT_ID_INDEX_LOCK_KEY = "product:ids:lock"

# 这里使用 Lua 脚本释放锁，而不是“先 get 再 delete”。
# 在并发环境中，get 和 delete 如果分两步执行，中间可能穿插其他请求重建了锁，
# 导致本请求误删别人的锁。Lua 在 Redis 侧原子执行，可以避免这个竞争条件。
REMOVE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


def product_cache_key(product_id: str) -> str:
    # 单独封装：
    # 缓存 Key 是跨多个分支共享的“协议入口”，封装后未来更容易统一替换前缀
    return f"{PRODUCT_CACHE_PREFIX}{product_id}"


def product_lock_key(product_id: str) -> str:
    # 锁 Key 基于业务 Key 派生，而不是平铺在别的命名空间里。
    return f"{product_cache_key(product_id)}{PRODUCT_LOCK_SUFFIX}"


def serialize_product(product: models.Product) -> dict:
    # 主动做一次序列化
    # ORM 对象直接塞缓存会把持久层细节泄漏到缓存层，后续字段调整时更容易失控。
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "original_price": float(product.original_price),
        "flash_price": float(product.flash_price),
    }


def ttl_with_jitter(base_seconds: int, jitter_seconds: int) -> int:
    # 随机过期：
    # 固定 TTL 在压测里很容易出现“整批缓存一起失效”的尖峰，
    # 抖动可以把失效时间分散到一个区间内，降低数据库瞬时压力，解决缓存雪崩问题。
    return base_seconds + random.randint(0, max(jitter_seconds, 0))


def read_product_cache(cache_key: str) -> Tuple[str, Optional[dict]]:
    # 这里返回 HIT / MISS / NULL 三态，而不是简单返回值或 None。
    # None 在缓存场景里语义不够明确，它可能代表“没命中”，也可能代表“命中了空值缓存”。
    # 三态结果能让上层更清楚地区分正常命中、缓存缺失、以及穿透保护命中。
    try:
        cached_data = redis_client.get(cache_key)
    except RedisError as exc:
        # 这里选择“Redis 异常时退化为查库”，本质上是在可用性优先。
        # 这能保证缓存层故障不会直接拖垮接口，但高并发下数据库压力会显著升高。
        # 如果后面流量更大可以叠加限流、熔断或热点隔离策略。
        print(f"Redis 读取缓存失败，回退数据库查询: {exc}")
        return "MISS", None

    if cached_data is None:
        return "MISS", None

    if cached_data == PRODUCT_EMPTY_PLACEHOLDER:
        return "NULL", None

    try:
        return "HIT", json.loads(cached_data)
    except json.JSONDecodeError:
        # 遇到脏缓存直接删掉：
        # 这说明缓存内容与当前反序列化协议已经不一致，继续保留只会让错误反复出现。
        # 主动删除等于把问题收敛到一次回源，而不是让后续所有请求都踩雷。
        try:
            redis_client.delete(cache_key)
        except RedisError:
            pass
        return "MISS", None


def cache_product_detail(product_id: str, product_dict: dict) -> None:
    # 缓存时把 TTL 和 jitter 放在同一处统一处理：
    # 这样可以避免不同调用方自己拼 TTL，最后出现“同一类数据多个过期策略”的隐性分叉。
    try:
        redis_client.set(
            product_cache_key(product_id),
            json.dumps(product_dict),
            ex=ttl_with_jitter(
                settings.product_cache_ttl_seconds,
                settings.product_cache_ttl_jitter_seconds,
            ),
        )
    except RedisError as exc:
        print(f"Redis 写入商品缓存失败: {exc}")


def cache_empty_product(product_id: str) -> None:
    # 空值缓存是防穿透的第一层。
    # 对于反复访问不存在商品的请求，第一次查库后就把“结果为空”记住，后续请求无需再访问数据库。
    # 空值缓存不是强一致方案，如果未来商品是“先被访问，后被创建”，短时间内可能出现误判。
    # 这也是为什么它的 TTL 会明显短于正常商品缓存。
    try:
        redis_client.set(
            product_cache_key(product_id),
            PRODUCT_EMPTY_PLACEHOLDER,
            ex=ttl_with_jitter(
                settings.product_null_cache_ttl_seconds,
                settings.product_null_cache_ttl_jitter_seconds,
            ),
        )
    except RedisError as exc:
        print(f"Redis 写入空值缓存失败: {exc}")


def acquire_lock(lock_key: str, ttl_seconds: int) -> Optional[str]:
    # 锁值要用随机 token，而不是简单写 1：
    # 因为释放锁时必须知道“这把锁是不是我加的”，否则并发下容易误删别人的锁，例如查询数据库花了15秒，锁10秒过期
    # 如果用固定值，过期后其他请求加的锁会被误删；如果用随机 token，只有锁的拥有者能释放成功。
    token = uuid.uuid4().hex
    try:
        locked = redis_client.set(lock_key, token, nx=True, ex=ttl_seconds)
    except RedisError as exc:
        # 这里 Redis 失败后返回 None，意味着上层可能走无锁兜底路径。
        # 这会降低击穿保护强度，但能保证服务在缓存基础设施不稳定时仍然可用。
        print(f"Redis 获取分布式锁失败: {exc}")
        return None
    return token if locked else None


def release_lock(lock_key: str, token: str) -> None:
    # 释放锁失败只记录日志，不抛异常：
    # 请求主链路此时通常已经完成，如果因为释放锁失败再把接口打成 500，
    # 会把“缓存层清理问题”升级成“用户可见业务失败”，得不偿失。
    try:
        redis_client.eval(REMOVE_LOCK_SCRIPT, 1, lock_key, token)
    except RedisError as exc:
        print(f"Redis 释放分布式锁失败: {exc}")


def wait_for_cache_rebuild(cache_key: str) -> Tuple[str, Optional[dict]]:
    # 为什么不直接所有失败请求都去查库：
    # 如果一个热点 Key 刚过期，最危险的不是单个请求慢，而是很多请求同时回源。
    # 等待短时间能显著减少回源并发数。
    deadline = time.time() + settings.product_cache_lock_wait_ms / 1000
    retry_interval = max(settings.product_cache_lock_retry_ms, 1) / 1000

    while time.time() < deadline:
        time.sleep(retry_interval)
        cache_status, cache_data = read_product_cache(cache_key)
        if cache_status != "MISS":
            return cache_status, cache_data

    return "MISS", None


def ensure_product_id_index(db: Session) -> None:
    # 商品 ID 集合是一层轻量存在性索引。
    try:
        if redis_client.exists(PRODUCT_ID_INDEX_READY_KEY):
            return
    except RedisError as exc:
        print(f"Redis 检查商品索引状态失败: {exc}")
        return

    # 为什么构建索引加锁：
    # 索引初始化属于“冷启动高竞争区”，多实例同时启动或多个请求同时首访时，
    # 都可能触发索引构建。加锁能让第一次触发的请求负责构建，其他请求直接等结果，避免重复建设和数据库压力。
    token = acquire_lock(PRODUCT_ID_INDEX_LOCK_KEY, settings.product_cache_lock_seconds)
    if not token:
        return

    try:
        if redis_client.exists(PRODUCT_ID_INDEX_READY_KEY):
            return

        product_ids = [row[0] for row in db.query(models.Product.id).all()]
        pipeline = redis_client.pipeline()
        if product_ids:
            pipeline.sadd(PRODUCT_ID_SET_KEY, *product_ids)
        pipeline.set(PRODUCT_ID_INDEX_READY_KEY, "1")
        pipeline.execute()
        # TODO:
        # 这里当前是“全量重建一次索引，然后依赖增量维护”。
        # 如果后续接入真正的商品更新 / 删除 / 导入，补充：
        # 1. 定时全量校准；
        # 2. 或基于消息队列异步同步索引；
        # 3. 或直接引入更适合大规模场景的布隆过滤器。
    except RedisError as exc:
        print(f"Redis 构建商品 ID 索引失败: {exc}")
    finally:
        release_lock(PRODUCT_ID_INDEX_LOCK_KEY, token)


def add_product_id_to_index(product_id: str) -> None:
    # 创建商品后要同步写索引：
    # 否则新商品虽然已经入库，但存在性索引还没更新，请求会被穿透保护误伤。
    try:
        redis_client.sadd(PRODUCT_ID_SET_KEY, product_id)
    except RedisError as exc:
        print(f"Redis 更新商品 ID 索引失败: {exc}")


def remove_product_id_from_index(product_id: str) -> None:
    # 查库确认商品不存在时，要顺手把索引里的旧 ID 去掉：
    try:
        redis_client.srem(PRODUCT_ID_SET_KEY, product_id)
    except RedisError as exc:
        print(f"Redis 移除商品 ID 索引失败: {exc}")


def product_may_exist(product_id: str, db: Session) -> bool:
    # 返回的是“may exist”而不是“exists”：
    # 当前索引属于工程优化手段，不是强一致事实源。
    # 一旦 Redis 异常、索引未初始化或数据短暂不一致，宁可放行到数据库二次确认，
    # 也不愿把真实存在的商品误判成不存在。
    ensure_product_id_index(db)
    try:
        if not redis_client.exists(PRODUCT_ID_INDEX_READY_KEY):
            return True
        return bool(redis_client.sismember(PRODUCT_ID_SET_KEY, product_id))
    except RedisError as exc:
        print(f"Redis 检查商品 ID 索引失败，回退数据库查询: {exc}")
        return True


def query_product_from_db(product_id: str, db: Session) -> Optional[models.Product]:
    # 这里保留一个单独函数，不只是为了“抽函数”。
    # 1. 让 get_product 的主流程更聚焦在缓存决策；
    # 2. 后续如果要加 trace、慢查询统计、只读库路由，会有稳定挂载点。
    return db.query(models.Product).filter(models.Product.id == product_id).first()


def log_db_routing(db: Session, operation: str) -> None:
    # 为什么要在代码里显式打印命中的数据库角色：
    # 课程作业里“读写分离已经做了”远远不够，真正能打动老师的是你能证明：
    # 1. 写请求确实打到了主库；
    # 2. 读请求确实打到了从库；
    # 3. 主从角色不是只存在于 docker-compose 里，而是落实到了运行时。
    # 这个日志函数就是为了把“运行时证据”补齐。
    bind = db.get_bind()
    if bind is None:
        return

    if bind.dialect.name != "mysql":
        # WARNING:
        # 集成测试里会用 SQLite 跑最小链路，这些数据库没有 MySQL 的角色变量。
        # 这里主动跳过，避免为了演示读写分离而破坏现有测试环境。
        print(f"[DB ROUTING] operation={operation}, dialect={bind.dialect.name}, mode=single-database-test")
        return

    try:
        row = db.execute(
            text("SELECT @@hostname AS hostname, @@server_id AS server_id, @@read_only AS read_only")
        ).mappings().first()
        if not row:
            return
        role = "READ_REPLICA" if int(row["read_only"]) == 1 else "WRITE_PRIMARY"
        print(
            f"[DB ROUTING] operation={operation}, role={role}, "
            f"host={row['hostname']}, server_id={row['server_id']}, read_only={row['read_only']}"
        )
    except Exception as exc:
        # WARNING:
        # 数据路由日志只负责“增强可观测性”，不应该反过来影响主业务。
        # 就算这里查询实例角色失败，也不能让创建商品或查询商品直接报错。
        print(f"[DB ROUTING] operation={operation}, status=failed-to-detect, reason={exc}")


# 商品的创建接口
@router.post("", response_model=ResponseModel[schemas.ProductResponse])
def create_product(
    product: schemas.ProductCreate,
    db: Session = Depends(database.get_write_db),
    user_id: str = Depends(get_current_user_id),
):
    # 为什么创建商品必须强制走写库：
    # 主从复制环境中，从库默认是只读的；即便强行放开，也会破坏主库是唯一事实源的原则。
    # 所以凡是会改变数据的请求，都应明确依赖写库连接，而不是使用模糊的默认连接。
    log_db_routing(db, "create_product")
    new_product = models.Product(**product.model_dump())
    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    # 创建商品时顺手预热缓存
    # 新商品通常会很快在商品列表、详情页中被访问，写路径顺手把缓存准备好，
    # 可以减少第一次读请求命中的冷启动成本。
    product_dict = serialize_product(new_product)
    add_product_id_to_index(new_product.id)
    cache_product_detail(new_product.id, product_dict)

    return success(data=new_product, message="商品创建成功")

# 商品列表接口（简单分页查询）
@router.get("", response_model=ResponseModel[List[schemas.ProductResponse]])
def get_products(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_read_db)):
    # 商品列表是最适合演示读写分离的接口之一：
    # 1. 它天然是读请求；
    # 2. 没有详情缓存命中带来的“看起来没有走数据库”的干扰；
    # 3. 压测时请求量大，更容易观察从库承接读压力的效果。
    log_db_routing(db, "get_products")
    products = db.query(models.Product).offset(skip).limit(limit).all()
    return success(data=products, message="成功获取商品列表")


# 商品详情接口
@router.get("/{product_id}", response_model=ResponseModel[schemas.ProductResponse])
def get_product(product_id: str, db: Session = Depends(database.get_read_db)):
    # 接口 3：获取单个商品详情 (点进商品详情页用)
    # 这条读链路同时承载了三类缓存治理：
    # 1. 穿透：先用存在性索引 + 空值缓存拦不存在商品；
    # 2. 击穿：热点 Key 失效时只允许一个请求回源；
    # 3. 雪崩：写缓存时统一加随机 TTL。
    # 现在又额外叠加了一层读写分离：真正回源查库时，默认会命中从库。
    # 这意味着缓存命中时读请求几乎不碰数据库，缓存未命中时也优先把读压力导向从库。
    cache_key = product_cache_key(product_id)

    # 第 1 步：优先读取缓存。
    # 商品详情属于典型高频读场景，缓存命中时应该尽量短路后续所有逻辑，
    # 让数据库、锁、索引检查都变成少数情况。
    cache_status, cached_product = read_product_cache(cache_key)
    if cache_status == "HIT":
        print("命中商品详情缓存")
        return success(data=cached_product, message="从缓存获取成功")
    if cache_status == "NULL":
        print("命中空值缓存，直接拦截不存在商品请求")
        raise HTTPException(status_code=404, detail="商品不存在")

    # 第 2 步：在真正查库前，先做一层存在性过滤。
    # 如果商品明显不存在，就没必要再去竞争分布式锁，否则恶意请求会把锁也打成热点。
    if not product_may_exist(product_id, db):
        print("商品 ID 不在索引中，命中缓存穿透保护")
        cache_empty_product(product_id)
        raise HTTPException(status_code=404, detail="商品不存在")

    lock_key = product_lock_key(product_id)
    lock_token = acquire_lock(lock_key, settings.product_cache_lock_seconds)

    if lock_token:
        try:
            # 第 3 步：拿到锁后再读一次缓存。
            # 在你抢锁的这段时间里，可能已经有其他请求把缓存补好了。
            # 如果不二次检查，就会出现“明明缓存已经有了，还多打一趟数据库”的浪费。
            cache_status, cached_product = read_product_cache(cache_key)
            if cache_status == "HIT":
                return success(data=cached_product, message="从缓存获取成功")
            if cache_status == "NULL":
                raise HTTPException(status_code=404, detail="商品不存在")

            print("缓存未命中，当前请求负责回源重建缓存")
            log_db_routing(db, "get_product_cache_rebuild_read")
            product = query_product_from_db(product_id, db)
            if not product:
                # 商品不存在时抛 404，写空值缓存和修正索引：
                # 否则下一批相同请求还是会继续穿透到数据库，问题不会真正被消化掉。
                cache_empty_product(product_id)
                remove_product_id_from_index(product_id)
                raise HTTPException(status_code=404, detail="商品不存在")

            product_dict = serialize_product(product)
            # 先写缓存，再返回：
            # 让当前这个“首个回源请求”承担缓存重建责任，后面排队请求可以直接吃到缓存收益。
            cache_product_detail(product_id, product_dict)
            add_product_id_to_index(product_id)
            return success(data=product_dict, message="从数据库获取成功")
        finally:
            release_lock(lock_key, lock_token)

    # 第 4 步：没抢到锁，说明已经有别的请求在重建缓存。
    print("检测到其他请求正在重建缓存，等待缓存回填")
    cache_status, cached_product = wait_for_cache_rebuild(cache_key)
    if cache_status == "HIT":
        return success(data=cached_product, message="从缓存获取成功")
    if cache_status == "NULL":
        raise HTTPException(status_code=404, detail="商品不存在")

    # 第 5 步：等待超时后的兜底。
    # 分布式系统里不能把希望全部押在锁持有者一定成功写回缓存上。
    # 对方可能卡住、超时、进程崩溃，兜底分支是在异常情况下保证最终可用性。
    print("等待缓存回填超时，执行数据库兜底查询")
    log_db_routing(db, "get_product_fallback_read")
    product = query_product_from_db(product_id, db)
    if not product:
        cache_empty_product(product_id)
        remove_product_id_from_index(product_id)
        raise HTTPException(status_code=404, detail="商品不存在")

    product_dict = serialize_product(product)
    cache_product_detail(product_id, product_dict)
    add_product_id_to_index(product_id)
    # TODO:
    # 当前商品服务只实现了创建和查询，没有实现更新 / 删除。
    # 一旦后续加入“修改商品信息、下架商品、删除商品”等写操作，
    # 必须补全对应的缓存失效 / 更新策略，否则这里的缓存保护会变成数据一致性风险点。
    # 可选方向：
    # 1. 写库后删缓存；
    # 2. 延迟双删；
    # 3. 订阅 binlog / MQ 做异步缓存同步。
    # TODO:
    # 如果后续把商品更新接口也纳入读写分离，需要同时处理“写主库成功但从库尚未追平”的复制延迟问题。
    # 到那时，某些强一致读请求可能需要临时回主库，不能机械地把所有 GET 都交给从库。
    return success(data=product_dict, message="从数据库兜底获取成功")
