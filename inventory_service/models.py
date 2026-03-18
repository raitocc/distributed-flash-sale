from sqlalchemy import Column, String, Integer
from database import Base


class Inventory(Base):
    __tablename__ = "inventory"

    # 直接用商品ID作为主键！因为一个商品对应一条库存记录，极其高效！
    product_id = Column(String(32), primary_key=True, index=True)

    # 真实总库存
    total_stock = Column(Integer, nullable=False, default=0)

    # 锁定库存 (下单未付款的占用量。可用库存 = total_stock - locked_stock)
    locked_stock = Column(Integer, nullable=False, default=0)