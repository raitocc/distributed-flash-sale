from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import httpx

import models
import schemas
import database
from config import settings
from core.security import get_current_user_id
from core.responses import success, ResponseModel

router = APIRouter(prefix="/api/orders", tags=["Orders"])

# ==========================================
# 🛒 1. 创建订单 (查价格 -> 锁库存 -> 生成订单)
# ==========================================
@router.post("", response_model=ResponseModel[schemas.OrderResponse])
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
        # 提取商品信息需要带上 .get("data")，或者先取 json
        res_json = prod_res.json()
        if prod_res.status_code != 200:
            raise HTTPException(status_code=prod_res.status_code, detail=res_json.get("message", "获取商品失败"))
        
        actual_price = res_json.get("data", {}).get("flash_price")

        # 🌟 步骤 B：去库存服务锁定库存
        inv_res = await client.post(inventory_deduct_url, json={"quantity": 1})
        if inv_res.status_code == 400:
            raise HTTPException(status_code=400, detail="哎呀，手慢了，商品已经被抢光啦！")
        elif inv_res.status_code != 200:
            raise HTTPException(status_code=500, detail="库存服务开小差了")

    # 步骤 C：库存锁成功了，安心落库
    new_order = models.Order(
        user_id=user_id, product_id=order_req.product_id, amount=actual_price, status="PENDING"
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)
    return success(data=new_order, message="订单创建成功")


# ==========================================
# 💰 2. 模拟付款成功
# ==========================================
@router.post("/{order_id}/pay", response_model=ResponseModel[dict])
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
    return success(data={"order_id": order_id, "status": "PAID"}, message="付款成功！老板大气！")


# ==========================================
# ❌ 3. 模拟取消订单
# ==========================================
@router.post("/{order_id}/cancel", response_model=ResponseModel[dict])
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
    return success(data={"order_id": order_id, "status": "CANCELLED"}, message="订单已取消，库存已为您释放。")
