from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy_utils import database_exists, create_database
from config import settings

engine = create_engine(settings.database_url)

# 自动检查并创建 flash_inventory_db
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