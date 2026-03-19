from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

import models
import schemas
import database
from config import settings
from core.security import get_current_user_id
from core.responses import success, ResponseModel

import json
import redis


# 初始化 Redis 客户端 (decode_responses=True 会自动把 byte 转成字符串)
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


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
# 接口 3：获取单个商品详情 (点进商品详情页用)
@router.get("/{product_id}", response_model=ResponseModel[schemas.ProductResponse])
def get_product(product_id: str, db: Session = Depends(database.get_db)):
    # 1. 定义这个商品在 Redis 里的唯一 Cache Key
    cache_key = f"product:{product_id}"

    # 2. 查缓存(Cache Hit)
    cached_data = redis_client.get(cache_key)
    if cached_data:
        print("命中缓存！从 Redis 返回数据！")
        # 注意：cached_data 已经是 JSON 字符串，反序列化后得到字典
        # 同样需要用 success 包装，否则 FastAPI 校验会报错
        return success(data=json.loads(cached_data), message="从缓存获取成功")

    # 3. 没命中查数据库 (Cache Miss)
    print("缓存未命中，从 MySQL 查询...")
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        # 这里用 HTTPException 是对的，它会被 FastAPI 自动处理
        raise HTTPException(status_code=404, detail="商品不存在")

    # 4. 把从数据库查到的结果，写进 Redis 留给下一个人用！
    # 因为不能直接存 Python 对象，要把它转成字典再变成 JSON 字符串
    product_dict = {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        # Numeric 类型要转成 float 才能被 JSON 序列化
        "original_price": float(product.original_price),
        "flash_price": float(product.flash_price)
    }

    # 极度重要：一定要设过期时间 (ex=3600 表示 1 小时后过期)！防止死数据占满内存
    redis_client.set(cache_key, json.dumps(product_dict), ex=3600)
    return success(data=product, message="从数据库获取成功")
