from pydantic import BaseModel

# 老板进货（初始化/增加库存）用的模型
class InventoryCreate(BaseModel):
    product_id: str
    total_stock: int  # 进货数量

# 扣减/锁定库存请求
class InventoryDeduct(BaseModel):
    quantity: int = 1 # 默认买1件

# 返回给前端的库存卡片
class InventoryResponse(BaseModel):
    product_id: str
    total_stock: int
    locked_stock: int
    available_stock: int # 可用库存（动态计算）

    class Config:
        from_attributes = True


class FlashSaleInventoryRequest(BaseModel):
    order_id: str
    user_id: str
    quantity: int = 1


class FlashSaleInventorySyncResponse(BaseModel):
    product_id: str
    redis_stock: int
