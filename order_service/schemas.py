from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# 核心安全理念：前端创建订单时，只允许传你要买啥！绝不允许传价格和用户ID！
class OrderCreate(BaseModel):
    product_id: str


class FlashSaleOrderEvent(BaseModel):
    order_id: str
    user_id: str
    product_id: str
    quantity: int = 1
    enqueue_time: datetime


class OrderSubmitResponse(BaseModel):
    order_id: str
    status: str
    message: str


# 返回给前端的订单详情
class OrderResponse(BaseModel):
    id: str
    user_id: str
    product_id: str
    amount: float
    quantity: int
    status: str
    failure_reason: Optional[str] = None
    create_time: datetime
    update_time: datetime

    class Config:
        from_attributes = True


class OrderStatusResponse(BaseModel):
    order_id: str
    user_id: str
    product_id: str
    quantity: int
    status: str
    message: str
    amount: Optional[float] = None
    failure_reason: Optional[str] = None
    create_time: Optional[datetime] = None
