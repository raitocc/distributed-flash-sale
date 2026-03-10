from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from typing import List

from starlette import status

import models
import schemas
import database
from config import settings
from database import engine

# 自动建表
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Product Service - 商品服务")

# 实例化，他会自动去请求头里找 Authorization: Bearer <token>
security = HTTPBearer()


# 鉴权依赖函数
def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        # 用一模一样的 SECRET_KEY 在本地解密验证
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        # 我们在 user_service 签发的时候，把用户 ID 存在了 "user_id" 这个字段里
        user_id: str = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的凭证")
        return user_id
    except JWTError:
        # 只要签名不对，或者过期了，jose 库就会抛出异常，保安直接拦截！
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 验证失败或已过期",
        )


# 接口 1：添加新商品
@app.post("/api/products", response_model=schemas.ProductResponse)
def create_product(product: schemas.ProductCreate, db: Session = Depends(database.get_db),
                   user_id: str = Depends(get_current_user_id)):
    print(f"当前操作的用户ID是: {user_id}")
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
