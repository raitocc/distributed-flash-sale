import time
from typing import Iterable

from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy_utils import create_database, database_exists

from config import settings


# 同时保留读引擎和写引擎
write_engine = create_engine(settings.effective_write_database_url)
read_engine = create_engine(settings.effective_read_database_url)

# 保留 engine 别名是为了兼容历史代码引用。
# WARNING:
# 新代码应尽量使用 write_engine / read_engine，而不是继续依赖模糊的 engine 概念。
engine = write_engine

# 写库负责数据库生命周期管理。
# 只在写库上 create_database：
# 主从复制要求从库的数据来源只能是主库的 binlog；
# 如果应用自己在从库上建库建表，就会破坏“主库是唯一事实源”这个前提。
if not database_exists(write_engine.url):
    create_database(write_engine.url)
    print(f"写库数据库 {write_engine.url.database} 已自动创建成功！")

WriteSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=write_engine)
ReadSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=read_engine)
Base = declarative_base()


def is_read_write_split_enabled() -> bool:
    # 单独抽一个判断：
    # 读写分离是“环境能力”，不是所有场景都存在。
    # 本地 SQLite 测试、单库调试、主从 Docker 环境都需要共用同一份代码。
    return settings.effective_write_database_url != settings.effective_read_database_url


def wait_for_read_replica_tables_ready(required_tables: Iterable[str], timeout_seconds: int = 30) -> None:
    # 在启动阶段等待从库表结构就绪：
    # 商品服务会在主库上 create_all，但表结构复制到从库不是瞬时完成的。
    # 如果应用一启动就立刻接受读请求，而从库还没同步到表结构，第一次读就可能直接报表不存在。
    # 这里主动等待，是把“复制尚未完成”的短暂窗口尽量收敛到服务启动期，而不是暴露给用户请求期。
    if not is_read_write_split_enabled():
        return

    required_table_set = set(required_tables)
    deadline = time.time() + timeout_seconds
    last_error = None

    while time.time() < deadline:
        try:
            inspector = inspect(read_engine)
            existing_tables = set(inspector.get_table_names())
            if required_table_set.issubset(existing_tables):
                print("读库表结构已同步完成，读写分离环境就绪。")
                return
        except SQLAlchemyError as exc:
            last_error = exc
        time.sleep(1)

    # WARNING:
    # 这里不抛异常，而是只打警告继续启动。
    # 原因是从库复制可能只是暂时变慢，如果直接让服务启动失败，演示环境的稳定性会更差。
    # 代价是启动后的前几个读请求仍可能因复制延迟失败，这也是读写分离天然需要面对的副作用。
    print(f"WARNING: 读库在 {timeout_seconds} 秒内未完成表结构同步，后续读请求可能受到复制延迟影响。最后一次错误: {last_error}")


def get_write_db():
    db = WriteSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_read_db():
    db = ReadSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db():
    # WARNING:
    # get_db 继续保留是为了兼容旧代码。
    # 但在读写分离改造完成后，新路由应明确声明自己依赖 get_write_db 还是 get_read_db，
    # 否则“默认走哪台库”会再次变得不透明。
    db = WriteSessionLocal()
    try:
        yield db
    finally:
        db.close()
