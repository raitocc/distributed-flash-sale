from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

import models
import schemas
import database
from core.security import get_current_user_id
from core.responses import success, ResponseModel

router = APIRouter(prefix="/api/products", tags=["Products"])

# 接口 1：添加新商品
@router.post("", response_model=ResponseModel[schemas.ProductResponse])
def create_product(product: schemas.ProductCreate, db: Session = Depends(database.get_db),
                   user_id: str = Depends(get_current_user_id)):
    new_product = models.Product(**product.model_dump())
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    return success(data=new_product, message="商品创建成功")

# 接口 2：获取商品列表 (秒杀大厅展示用)
@router.get("", response_model=ResponseModel[List[schemas.ProductResponse]])
def get_products(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    products = db.query(models.Product).offset(skip).limit(limit).all()
    return success(data=products, message="成功获取商品列表")

# 接口 3：获取单个商品详情 (点进商品详情页用)
@router.get("/{product_id}", response_model=ResponseModel[schemas.ProductResponse])
def get_product(product_id: str, db: Session = Depends(database.get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    return success(data=product, message="成功获取商品详情")
