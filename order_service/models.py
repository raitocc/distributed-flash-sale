from sqlalchemy import Column, String, DateTime, Numeric
from datetime import datetime, timezone
import uuid6
from database import Base


def generate_uuid7():
    return uuid6.uuid7().hex


class Order(Base):
    __tablename__ = "orders"

    # 订单号 (主键，依然使用高性能的 UUIDv7)
    id = Column(String(32), primary_key=True, default=generate_uuid7, index=True)

    # 核心关联字段：买家ID 和 商品ID
    user_id = Column(String(32), index=True, nullable=False)
    product_id = Column(String(32), index=True, nullable=False)

    # 订单快照数据：下单时的真实成交价 (极其重要！因为商品价格以后可能会变)
    amount = Column(Numeric(10, 2), nullable=False)

    # 订单状态 (默认刚下完单是 待支付 PENDING)
    status = Column(String(20), default="PENDING")

    # 创建时间
    create_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))