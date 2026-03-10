# 数据库user表结构映射
import uuid6
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
from database import Base

# 生成 32 位去横杠的 UUIDv7 字符串
def generate_uuid7():
    return uuid6.uuid7().hex

class User(Base):
    __tablename__ = "users" # MySQL 中的表名

    id = Column(String(32), primary_key=True, default=generate_uuid7, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    # email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False) # 存加密后的密码
    create_time = Column(DateTime, default=datetime.now)