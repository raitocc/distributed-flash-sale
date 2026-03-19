from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import schemas
import database
from core.responses import success, ResponseModel

router = APIRouter(prefix="/api/inventory", tags=["Inventory"])

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
    else:
        # 如果没有，就在仓库里腾个新位置
        inventory = models.Inventory(
            product_id=inv_req.product_id,
            total_stock=inv_req.total_stock,
            locked_stock=0
        )
        db.add(inventory)

    db.commit()
    db.refresh(inventory)

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
# 接口 3：扣库存（最基础版 - 暂不考虑高并发超卖）
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
# 接口 4：付款成功 -> 确认真实扣减
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
    return success(data=None, message="付款成功，库存真实扣减完毕！")

# -----------------------------------------------------------------
# 接口 5：取消订单 -> 释放锁定的库存
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
