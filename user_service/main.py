from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

import models
import database
from database import engine

from core.exceptions import http_exception_handler, validation_exception_handler, global_exception_handler
from api.routes import router as users_router

# 自动在 MySQL 中建表
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="User Service - 注册与登录")

# 注册异常处理
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# 注册路由
app.include_router(users_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)