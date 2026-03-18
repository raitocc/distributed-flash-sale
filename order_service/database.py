from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy_utils import database_exists, create_database
from config import settings

# 创建引擎
engine = create_engine(settings.database_url)

# 程序启动时检查，如果没有 flash_order_db 这个库，就自动建一个！
if not database_exists(engine.url):
    create_database(engine.url)
    print(f"数据库 {engine.url.database} 已自动创建成功！")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()