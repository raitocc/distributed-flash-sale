from pydantic import BaseModel
from typing import Optional

# 创建商品时前端传的数据
class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    original_price: float
    flash_price: float

# 返回给前端的商品数据
class ProductResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    original_price: float
    flash_price: float

    class Config:
        from_attributes = True