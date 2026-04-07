from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

import models
import database
from database import write_engine

from core.exceptions import http_exception_handler, validation_exception_handler, global_exception_handler
from api.routes import router as products_router

def initialize_schema() -> None:
    # 在这里显式加一层 MySQL 命名锁：
    # 当前商品服务会启动多个副本来配合 Nginx 做负载均衡演示。
    # 如果三个副本同时执行 create_all()，SQLAlchemy 虽然会先检查表是否存在，
    # 但这个“检查 -> 建表”并不是分布式原子操作，多个副本仍可能在毫秒级竞争窗口里一起尝试 CREATE TABLE，
    # 最终让后启动的副本报出 “Table already exists” 并退出。
    # 用数据库命名锁把建表阶段串行化，可以把这个只会在多副本冷启动时出现的竞争条件收敛掉。
    with write_engine.begin() as connection:
        lock_acquired = False
        lock_name = "product_service_schema_init"

        if connection.dialect.name == "mysql":
            lock_acquired = bool(
                connection.execute(
                    text("SELECT GET_LOCK(:lock_name, :timeout_seconds)"),
                    {"lock_name": lock_name, "timeout_seconds": 30},
                ).scalar()
            )
            # WARNING:
            # 如果这里拿不到锁，说明已有其他副本正在做 schema 初始化。
            # 直接继续 create_all 只会把竞争问题重新带回来，因此这里主动失败更容易暴露异常环境。
            if not lock_acquired:
                raise RuntimeError("商品服务初始化表结构时未能获得数据库锁，请检查其他副本是否卡住")

        try:
            # 自动建表只在写库执行。
            # 在读写分离场景下，主库是唯一允许承接 DDL / DML 的事实源，
            # 从库应该通过复制追平，而不是由应用直接改写。
            models.Base.metadata.create_all(bind=connection)
        except OperationalError as exc:
            # 为什么这里把 “already exists” 视为可恢复：
            # 在多副本同时冷启动时，就算已经有锁保护，仍可能遇到历史遗留实例刚刚完成建表、
            # 而当前副本读到的是稍旧的元数据视图。此时表已存在说明目标状态已经达成，
            # 没必要把整个服务启动打成失败。
            if "already exists" not in str(exc).lower():
                raise
            print(f"检测到并发建表竞争，但表结构已存在，继续启动即可: {exc}")
        finally:
            if lock_acquired:
                connection.execute(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": lock_name})


initialize_schema()

# 建表后要额外等待读库：
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
