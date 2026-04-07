from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

import models
import database
from database import write_engine

from core.exceptions import http_exception_handler, validation_exception_handler, global_exception_handler
from api.routes import router as products_router

# 自动建表只在写库执行。
# 为什么：
# 在读写分离场景下，主库是唯一允许承接 DDL / DML 的事实源，
# 从库应该通过复制追平，而不是由应用直接改写。
models.Base.metadata.create_all(bind=write_engine)

# 为什么建表后要额外等待读库：
# 商品服务的读请求会直接打到从库，如果从库还没同步到最新表结构，
# 应用虽然已经“启动成功”，但第一次读请求就可能失败。
database.wait_for_read_replica_tables_ready(models.Base.metadata.tables.keys())

app = FastAPI(title="Product Service - 商品服务")

# 注册异常处理
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# 注册路由
app.include_router(products_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
