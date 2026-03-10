from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

import models
import schemas
import database
from database import engine

# 自动建表
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Product Service - 商品服务")

# 接口 1：添加新商品 (为了方便测试，先不加权限校验)
@app.post("/api/products", response_model=schemas.ProductResponse)
def create_product(product: schemas.ProductCreate, db: Session = Depends(database.get_db)):
    new_product = models.Product(**product.model_dump())
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    return new_product

# 接口 2：获取商品列表 (秒杀大厅展示用)
@app.get("/api/products", response_model=List[schemas.ProductResponse])
def get_products(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    products = db.query(models.Product).offset(skip).limit(limit).all()
    return products

# 接口 3：获取单个商品详情 (点进商品详情页用)
@app.get("/api/products/{product_id}", response_model=schemas.ProductResponse)
def get_product(product_id: str, db: Session = Depends(database.get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    return product

if __name__ == "__main__":
    import uvicorn
    # 注意！商品服务必须跑在不同的端口，比如 8002
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)