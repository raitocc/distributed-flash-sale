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
# 🛒 模块二：核心下单接口 (跨服务调用实战)
# ==========================================
@app.post("/api/orders", response_model=schemas.OrderResponse)
async def create_order(
        order_req: schemas.OrderCreate,
        db: Session = Depends(database.get_db),
        user_id: str = Depends(get_current_user_id)
):
    # 步骤 A：拼装商品服务的 API 地址
    product_url = f"{settings.product_service_url}/api/products/{order_req.product_id}"

    # 步骤 B：发起异步 HTTP 请求，去问商品服务要数据！
    async with httpx.AsyncClient() as client:
        try:
            # 就像你在浏览器里回车一样，给 8002 端口发个 GET 请求
            response = await client.get(product_url)
        except httpx.RequestError:
            # 万一商品服务挂了，咱们得有优雅的报错
            raise HTTPException(status_code=503, detail="商品服务开小差了，请稍后再试")

    # 步骤 C：处理商品服务的回答
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="您要买的商品不存在呀！")
    elif response.status_code != 200:
        raise HTTPException(status_code=500, detail="获取商品价格失败，请联系客服")

    # 步骤 D：提取秒杀价
    product_data = response.json()
    actual_price = product_data.get("flash_price")

    # 步骤 E：落库生成订单！
    new_order = models.Order(
        user_id=user_id,
        product_id=order_req.product_id,
        amount=actual_price,
        status="PENDING"
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    return new_order


if __name__ == "__main__":
    import uvicorn

    # 订单服务跑在 8003 端口
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True)