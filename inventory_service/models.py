from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String
from database import Base


class Inventory(Base):
    __tablename__ = "inventory"

    # 直接用商品ID作为主键！因为一个商品对应一条库存记录，极其高效！
    product_id = Column(String(32), primary_key=True, index=True)

    # 真实总库存
    total_stock = Column(Integer, nullable=False, default=0)

    # 锁定库存 (下单未付款的占用量。可用库存 = total_stock - locked_stock)
    locked_stock = Column(Integer, nullable=False, default=0)


class FlashSaleInventoryRecord(Base):
    __tablename__ = "flash_sale_inventory_records"

    # 为什么库存确认要单独建一张幂等记录表：
    # Kafka 至少一次投递意味着“同一条下单消息被消费两次”不是异常，而是需要正面处理的常态。
    # 如果库存服务没有自己的操作日志，就无法证明“这个 order_id 我到底扣过没有”。
    order_id = Column(String(32), primary_key=True)
    product_id = Column(String(32), index=True, nullable=False)
    user_id = Column(String(32), index=True, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="CONFIRMED")
    create_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    update_time = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
