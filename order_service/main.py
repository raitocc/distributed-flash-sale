from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

import models
from database import engine

from core.exceptions import http_exception_handler, validation_exception_handler, global_exception_handler
from api.routes import router as orders_router
from flash_sale import close_kafka_producer
from order_consumer import start_flash_sale_consumer, stop_flash_sale_consumer

# 自动建表
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Order Service - 订单服务")

# 注册异常处理
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

@app.on_event("startup")
def startup_event():
    # 为什么在服务启动时就拉起消费者：
    # 秒杀入口已经把请求转成了 Kafka 消息，如果消费者不跟着启动，就会出现“前台一直排队、后台没人处理”的假成功。
    start_flash_sale_consumer()


@app.on_event("shutdown")
def shutdown_event():
    stop_flash_sale_consumer()
    close_kafka_producer()


# 注册路由
app.include_router(orders_router)

if __name__ == "__main__":
    import uvicorn
    # 订单服务跑在 8003 端口
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True)
