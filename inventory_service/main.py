from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session

import models
import schemas
import database
from database import engine

# 启动时自动建表！
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Inventory Service - 库存服务")


# -----------------------------------------------------------------
# 接口 1：老板进货 (设置或增加库存)
# -----------------------------------------------------------------
@app.post("/api/inventory", response_model=schemas.InventoryResponse)
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
    return schemas.InventoryResponse(
        product_id=inventory.product_id,
        total_stock=inventory.total_stock,
        locked_stock=inventory.locked_stock,
        available_stock=inventory.total_stock - inventory.locked_stock
    )


# -----------------------------------------------------------------
# 接口 2：查库存 (看看还剩多少)
# -----------------------------------------------------------------
@app.get("/api/inventory/{product_id}", response_model=schemas.InventoryResponse)
def get_inventory(product_id: str, db: Session = Depends(database.get_db)):
    inventory = db.query(models.Inventory).filter(models.Inventory.product_id == product_id).first()
    if not inventory:
        raise HTTPException(status_code=404, detail="仓库里没这个商品的库存记录")

    return schemas.InventoryResponse(
        product_id=inventory.product_id,
        total_stock=inventory.total_stock,
        locked_stock=inventory.locked_stock,
        available_stock=inventory.total_stock - inventory.locked_stock
    )


# -----------------------------------------------------------------
# 接口 3：扣库存（最基础版 - 暂不考虑高并发超卖）
# -----------------------------------------------------------------
@app.post("/api/inventory/{product_id}/deduct")
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

    return {"message": "库存锁定成功！", "locked_quantity": deduct_req.quantity}


# -----------------------------------------------------------------
# 接口 4：付款成功 -> 确认真实扣减
# -----------------------------------------------------------------
@app.post("/api/inventory/{product_id}/confirm")
def confirm_inventory(product_id: str, deduct_req: schemas.InventoryDeduct, db: Session = Depends(database.get_db)):
    inventory = db.query(models.Inventory).filter(models.Inventory.product_id == product_id).first()
    if not inventory or inventory.locked_stock < deduct_req.quantity:
        raise HTTPException(status_code=400, detail="数据异常：没有足够的锁定库存可供确认！")

    # 核心：总库存真正减少了，锁定的名额也释放了
    inventory.total_stock -= deduct_req.quantity
    inventory.locked_stock -= deduct_req.quantity
    db.commit()
    return {"message": "付款成功，库存真实扣减完毕！"}


# -----------------------------------------------------------------
# 接口 5：取消订单 -> 释放锁定的库存
# -----------------------------------------------------------------
@app.post("/api/inventory/{product_id}/release")
def release_inventory(product_id: str, deduct_req: schemas.InventoryDeduct, db: Session = Depends(database.get_db)):
    inventory = db.query(models.Inventory).filter(models.Inventory.product_id == product_id).first()
    if not inventory or inventory.locked_stock < deduct_req.quantity:
        raise HTTPException(status_code=400, detail="数据异常：没有锁定的库存可供释放！")

    # 核心：只把锁定的名额还回去，总库存不动
    inventory.locked_stock -= deduct_req.quantity
    db.commit()
    return {"message": "订单已取消，库存已重新释放回奖池！"}

if __name__ == "__main__":
    import uvicorn

    # 专属的 8004 端口！
    uvicorn.run("main:app", host="0.0.0.0", port=8004, reload=True)