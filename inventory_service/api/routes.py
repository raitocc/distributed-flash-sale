from fastapi import APIRouter, Depends, HTTPException, Query
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

import database
import models
import redis
import schemas
from config import settings
from core.responses import ResponseModel, success


router = APIRouter(prefix="/api/inventory", tags=["Inventory"])
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

FLASH_SALE_STOCK_PREFIX = "flashsale:stock:"


def flash_sale_stock_key(product_id: str) -> str:
    return f"{FLASH_SALE_STOCK_PREFIX}{product_id}"


def get_flash_sale_stock(product_id: str) -> int | None:
    try:
        stock = redis_client.get(flash_sale_stock_key(product_id))
    except RedisError as exc:
        raise HTTPException(status_code=503, detail=f"Redis 库存服务不可用: {exc}") from exc
    return int(stock) if stock is not None else None


def set_flash_sale_stock(product_id: str, stock: int) -> int:
    try:
        redis_client.set(flash_sale_stock_key(product_id), stock)
    except RedisError as exc:
        raise HTTPException(status_code=503, detail=f"Redis 库存回写失败: {exc}") from exc
    return stock


def increase_flash_sale_stock(product_id: str, delta: int) -> int:
    try:
        if redis_client.exists(flash_sale_stock_key(product_id)):
            return int(redis_client.incrby(flash_sale_stock_key(product_id), delta))
        # 为什么 Key 缺失时不盲目只做 incr：
        # 如果 Redis 因为重启丢了数据，而数据库里已经是“扣减后的剩余库存”，
        # 单纯按 delta 自增会从 0 开始算，结果会把真实库存算得更少或更乱。
        db = database.SessionLocal()
        try:
            inventory = db.query(models.Inventory).filter(models.Inventory.product_id == product_id).first()
        finally:
            db.close()
        if not inventory:
            raise HTTPException(status_code=404, detail="商品库存不存在")
        redis_client.set(flash_sale_stock_key(product_id), inventory.total_stock)
        return inventory.total_stock
    except RedisError as exc:
        raise HTTPException(status_code=503, detail=f"Redis 库存更新失败: {exc}") from exc


def preload_flash_sale_stock(product_id: str, db: Session, force: bool = False) -> int:
    inventory = db.query(models.Inventory).filter(models.Inventory.product_id == product_id).first()
    if not inventory:
        raise HTTPException(status_code=404, detail="仓库里没这个商品的库存记录")

    # WARNING:
    # force=True 会直接用数据库剩余库存覆盖 Redis。
    # 这在“干净启动、刚初始化库存、尚无积压消息”的课堂演示环境里是安全的，
    # 但如果线上存在尚未消费完的 Kafka 积压订单，这么做会抹掉 Redis 已预扣但数据库尚未落账的差值。
    if not force:
        current_stock = get_flash_sale_stock(product_id)
        if current_stock is not None:
            return current_stock

    return set_flash_sale_stock(product_id, inventory.total_stock)


# -----------------------------------------------------------------
# 接口 1：老板进货 (设置或增加库存)
# -----------------------------------------------------------------
@router.post("", response_model=ResponseModel[schemas.InventoryResponse])
def set_inventory(inv_req: schemas.InventoryCreate, db: Session = Depends(database.get_db)):
    # 查查仓库里有没有这个商品
    inventory = db.query(models.Inventory).filter(models.Inventory.product_id == inv_req.product_id).first()

    if inventory:
        # 如果有，就在原基础上加库存
        inventory.total_stock += inv_req.total_stock
        db.commit()
        redis_stock = increase_flash_sale_stock(inv_req.product_id, inv_req.total_stock)
    else:
        # 如果没有，就在仓库里腾个新位置
        inventory = models.Inventory(
            product_id=inv_req.product_id,
            total_stock=inv_req.total_stock,
            locked_stock=0
        )
        db.add(inventory)
        db.commit()
        redis_stock = set_flash_sale_stock(inv_req.product_id, inv_req.total_stock)

    db.refresh(inventory)

    # 为什么“新增库存”时优先做增量同步而不是总量覆盖：
    # Redis 里的 flash sale stock 代表的是“已经扣除了排队订单后的可售名额”，
    # 它和数据库 total_stock 在异步消费期间可能短暂不完全相等。
    # 管理员补货应该增加可售量，但不能把已排队扣掉的差值抹平，所以这里用 delta 增加更安全。
    print(f"[FLASH STOCK] product_id={inv_req.product_id}, redis_stock={redis_stock}")

    # 组装返回数据，顺便计算一下可用库存返回
    return success(
        message="库存设置成功",
        data=schemas.InventoryResponse(
            product_id=inventory.product_id,
            total_stock=inventory.total_stock,
            locked_stock=inventory.locked_stock,
            available_stock=inventory.total_stock - inventory.locked_stock
        )
    )


# -----------------------------------------------------------------
# 接口 2：查库存 (看看还剩多少)
# -----------------------------------------------------------------
@router.get("/{product_id}", response_model=ResponseModel[schemas.InventoryResponse])
def get_inventory(product_id: str, db: Session = Depends(database.get_db)):
    inventory = db.query(models.Inventory).filter(models.Inventory.product_id == product_id).first()
    if not inventory:
        raise HTTPException(status_code=404, detail="仓库里没这个商品的库存记录")

    return success(
        message="查询库存成功",
        data=schemas.InventoryResponse(
            product_id=inventory.product_id,
            total_stock=inventory.total_stock,
            locked_stock=inventory.locked_stock,
            available_stock=inventory.total_stock - inventory.locked_stock
        )
    )


# -----------------------------------------------------------------
# 接口 3：预热秒杀库存缓存
# -----------------------------------------------------------------
@router.post("/{product_id}/flash-sale/preload", response_model=ResponseModel[schemas.FlashSaleInventorySyncResponse])
def preload_inventory_for_flash_sale(
    product_id: str,
    force: bool = Query(default=False),
    db: Session = Depends(database.get_db),
):
    redis_stock = preload_flash_sale_stock(product_id, db, force=force)
    return success(
        message="秒杀库存缓存预热成功",
        data=schemas.FlashSaleInventorySyncResponse(product_id=product_id, redis_stock=redis_stock),
    )


# -----------------------------------------------------------------
# 接口 4：秒杀订单成功消费后，最终扣减数据库库存
# -----------------------------------------------------------------
@router.post("/{product_id}/flash-sale/commit", response_model=ResponseModel[dict])
def commit_flash_sale_inventory(
    product_id: str,
    req: schemas.FlashSaleInventoryRequest,
    db: Session = Depends(database.get_db),
):
    record = db.query(models.FlashSaleInventoryRecord).filter(models.FlashSaleInventoryRecord.order_id == req.order_id).first()
    if record:
        if record.product_id != product_id or record.user_id != req.user_id:
            raise HTTPException(status_code=400, detail="订单库存扣减记录与当前请求不匹配")
        # 为什么重复消费要直接返回成功：
        # Kafka 至少一次投递的语义决定了“同一消息被消费两次”是正常现象。
        # 真正的幂等不是“不要出现重复消息”，而是“重复消息来了，结果仍然和处理一次完全一致”。
        if record.status == "CONFIRMED":
            return success(
                data={"order_id": req.order_id, "status": "CONFIRMED"},
                message="库存已确认扣减，无需重复处理",
            )
        if record.status == "RESTORED":
            return success(
                data={"order_id": req.order_id, "status": "RESTORED"},
                message="该订单库存已回补，不再重复扣减",
            )

    inventory = (
        db.query(models.Inventory)
        .filter(models.Inventory.product_id == product_id)
        .with_for_update()
        .first()
    )
    if not inventory:
        raise HTTPException(status_code=404, detail="商品库存记录不存在")
    if inventory.total_stock < req.quantity:
        # WARNING:
        # 这里出现不足，说明 Redis 预扣和数据库最终扣减已经脱节。
        # 正常情况下 Redis 闸门应该先把超卖挡住，所以这里更像“系统告警点”，而不是普通业务提示。
        raise HTTPException(status_code=409, detail="数据库剩余库存不足，检测到库存一致性冲突")

    inventory.total_stock -= req.quantity
    db.add(
        models.FlashSaleInventoryRecord(
            order_id=req.order_id,
            product_id=product_id,
            user_id=req.user_id,
            quantity=req.quantity,
            status="CONFIRMED",
        )
    )
    db.commit()
    return success(data={"order_id": req.order_id, "status": "CONFIRMED"}, message="秒杀库存已最终扣减")


# -----------------------------------------------------------------
# 接口 5：取消订单后，回补数据库与 Redis 库存
# -----------------------------------------------------------------
@router.post("/{product_id}/flash-sale/restore", response_model=ResponseModel[dict])
def restore_flash_sale_inventory(
    product_id: str,
    req: schemas.FlashSaleInventoryRequest,
    db: Session = Depends(database.get_db),
):
    record = db.query(models.FlashSaleInventoryRecord).filter(models.FlashSaleInventoryRecord.order_id == req.order_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="没有找到这笔秒杀库存扣减记录")
    if record.product_id != product_id or record.user_id != req.user_id:
        raise HTTPException(status_code=400, detail="订单库存回补记录与当前请求不匹配")
    if record.status == "RESTORED":
        return success(data={"order_id": req.order_id, "status": "RESTORED"}, message="库存已经回补过了")

    inventory = (
        db.query(models.Inventory)
        .filter(models.Inventory.product_id == product_id)
        .with_for_update()
        .first()
    )
    if not inventory:
        raise HTTPException(status_code=404, detail="商品库存记录不存在")

    inventory.total_stock += req.quantity
    record.status = "RESTORED"
    db.commit()

    # 为什么订单取消后的 Redis 回补要放在数据库提交之后：
    # 因为最终事实源仍然是数据库。如果先把 Redis 加回去，后续数据库提交失败，
    # 用户层面看到的是“库存又能抢了”，但持久化库存其实没恢复，最终会把问题重新推成超卖风险。
    latest_stock = increase_flash_sale_stock(product_id, req.quantity)
    print(f"[FLASH STOCK RESTORE] product_id={product_id}, redis_stock={latest_stock}")
    return success(data={"order_id": req.order_id, "status": "RESTORED"}, message="库存已回补")


# -----------------------------------------------------------------
# 接口 6：扣库存（最基础版 - 暂不考虑高并发超卖）
# -----------------------------------------------------------------
@router.post("/{product_id}/deduct", response_model=ResponseModel[dict])
def deduct_inventory(product_id: str, deduct_req: schemas.InventoryDeduct, db: Session = Depends(database.get_db)):
    inventory = db.query(models.Inventory).filter(models.Inventory.product_id == product_id).first()

    if not inventory:
        raise HTTPException(status_code=404, detail="商品库存记录不存在")

    # 核心判断逻辑：真实总库存 - 已经被别人锁定的库存 = 你现在能买的库存
    available = inventory.total_stock - inventory.locked_stock
    if available < deduct_req.quantity:
        raise HTTPException(status_code=400, detail="手慢了，库存不足啦！")

    # 库存够！直接把这部分库存锁定（等用户真付了钱，再从 total_stock 里真扣）
    inventory.locked_stock += deduct_req.quantity
    db.commit()

    return success(data={"locked_quantity": deduct_req.quantity}, message="库存锁定成功！")


# -----------------------------------------------------------------
# 接口 7：付款成功 -> 确认真实扣减
# -----------------------------------------------------------------
@router.post("/{product_id}/confirm", response_model=ResponseModel[dict])
def confirm_inventory(product_id: str, deduct_req: schemas.InventoryDeduct, db: Session = Depends(database.get_db)):
    inventory = db.query(models.Inventory).filter(models.Inventory.product_id == product_id).first()
    if not inventory or inventory.locked_stock < deduct_req.quantity:
        raise HTTPException(status_code=400, detail="数据异常：没有足够的锁定库存可供确认！")

    # 核心：总库存真正减少了，锁定的名额也释放了
    inventory.total_stock -= deduct_req.quantity
    inventory.locked_stock -= deduct_req.quantity
    db.commit()

    # TODO:
    # 这里保留了旧版“锁库存 -> 付款确认”的同步接口，方便和秒杀异步方案做对比。
    # 如果后续决定整个系统都统一走 Redis 预扣 + Kafka 异步建单，就可以考虑逐步下线这一套老接口。
    return success(data=None, message="付款成功，库存真实扣减完毕！")


# -----------------------------------------------------------------
# 接口 8：取消订单 -> 释放锁定的库存
# -----------------------------------------------------------------
@router.post("/{product_id}/release", response_model=ResponseModel[dict])
def release_inventory(product_id: str, deduct_req: schemas.InventoryDeduct, db: Session = Depends(database.get_db)):
    inventory = db.query(models.Inventory).filter(models.Inventory.product_id == product_id).first()
    if not inventory or inventory.locked_stock < deduct_req.quantity:
        raise HTTPException(status_code=400, detail="数据异常：没有锁定的库存可供释放！")

    # 核心：只把锁定的名额还回去，总库存不动
    inventory.locked_stock -= deduct_req.quantity
    db.commit()
    return success(data=None, message="订单已取消，库存已重新释放回奖池！")
