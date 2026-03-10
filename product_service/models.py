from sqlalchemy import Column, String, DateTime, Numeric, Text
from datetime import datetime, timezone
import uuid6
from database import Base

def generate_uuid7():
    return uuid6.uuid7().hex

class Product(Base):
    __tablename__ = "products"

    id = Column(String(32), primary_key=True, default=generate_uuid7, index=True)
    name = Column(String(100), index=True, nullable=False)  # 商品名称
    description = Column(Text, nullable=True)               # 商品描述
    original_price = Column(Numeric(10, 2), nullable=False) # 原价 (最大99999999.99)
    flash_price = Column(Numeric(10, 2), nullable=False)    # 秒杀价
    create_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))