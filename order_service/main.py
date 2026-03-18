from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import JWTError, jwt
import httpx  # 跨服务调用

import models
import schemas
import database
from config import settings
from database import engine

# 自动建表 (配合之前写的 sqlalchemy-utils，连数据库都会自动建好！)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Order Service - 订单服务")

# ==========================================
# 模块一：JWT (直接从商品服务复制过来的)
# ==========================================
security = HTTPBearer()


def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        # 用配置里的密钥验证
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的凭证")
        return user_id
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 验证失败或已过期")


# ==========================================
# 🛒 1. 创建订单 (查价格 -> 锁库存 -> 生成订单)
# ==========================================
@app.post("/api/orders", response_model=schemas.OrderResponse)
async def create_order(
        order_req: schemas.OrderCreate,
        db: Session = Depends(database.get_db),
        user_id: str = Depends(get_current_user_id)
):
    product_url = f"{settings.product_service_url}/api/products/{order_req.product_id}"
    inventory_deduct_url = f"{settings.inventory_service_url}/api/inventory/{order_req.product_id}/deduct"

    async with httpx.AsyncClient() as client:
        # 步骤 A：去问商品服务要价格
        prod_res = await client.get(product_url)
        if prod_res.status_code == 404:
            raise HTTPException(status_code=404, detail="商品不存在")
        actual_price = prod_res.json().get("flash_price")

        # 🌟 步骤 B：去库存服务【锁定库存】！
        inv_res = await client.post(inventory_deduct_url, json={"quantity": 1})
        if inv_res.status_code == 400:
            raise HTTPException(status_code=400, detail="哎呀，手慢了，商品已经被抢光啦！")
        elif inv_res.status_code != 200:
            raise HTTPException(status_code=500, detail="库存服务开小差了")

    # 步骤 C：库存锁成功了，安心落库！
    new_order = models.Order(
        user_id=user_id, product_id=order_req.product_id, amount=actual_price, status="PENDING"
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)
    return new_order


# ==========================================
# 💰 2. 模拟付款成功
# ==========================================
@app.post("/api/orders/{order_id}/pay")
async def pay_order(order_id: str, db: Session = Depends(database.get_db), user_id: str = Depends(get_current_user_id)):
    order = db.query(models.Order).filter(models.Order.id == order_id, models.Order.user_id == user_id).first()
    if not order or order.status != "PENDING":
        raise HTTPException(status_code=400, detail="订单不存在或状态不正确")

    # 去库存服务【确认扣减】
    confirm_url = f"{settings.inventory_service_url}/api/inventory/{order.product_id}/confirm"
    async with httpx.AsyncClient() as client:
        await client.post(confirm_url, json={"quantity": 1})

    # 改状态
    order.status = "PAID"
    db.commit()
    return {"message": "付款成功！老板大气！"}


# ==========================================
# ❌ 3. 模拟取消订单
# ==========================================
@app.post("/api/orders/{order_id}/cancel")
async def cancel_order(order_id: str, db: Session = Depends(database.get_db),
                       user_id: str = Depends(get_current_user_id)):
    order = db.query(models.Order).filter(models.Order.id == order_id, models.Order.user_id == user_id).first()
    if not order or order.status != "PENDING":
        raise HTTPException(status_code=400, detail="订单不存在或无法取消")

    # 去库存服务【释放库存】
    release_url = f"{settings.inventory_service_url}/api/inventory/{order.product_id}/release"
    async with httpx.AsyncClient() as client:
        await client.post(release_url, json={"quantity": 1})

    # 改状态
    order.status = "CANCELLED"
    db.commit()
    return {"message": "订单已取消，库存已为您释放。"}


if __name__ == "__main__":
    import uvicorn

    # 订单服务跑在 8003 端口
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True)