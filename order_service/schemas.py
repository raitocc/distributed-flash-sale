from pydantic import BaseModel
from datetime import datetime

# 核心安全理念：前端创建订单时，只允许传你要买啥！绝不允许传价格和用户ID！
class OrderCreate(BaseModel):
    product_id: str

# 返回给前端的订单详情
class OrderResponse(BaseModel):
    id: str
    user_id: str
    product_id: str
    amount: float
    status: str
    create_time: datetime

    class Config:
        from_attributes = True