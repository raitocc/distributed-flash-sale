# Pydantic 数据模型（负责校验前端传来的 JSON）
from pydantic import BaseModel, EmailStr

# 注册时前端需要传的数据
class UserCreate(BaseModel):
    username: str
    # email: EmailStr
    password: str

# 登录时前端需要传的数据
class UserLogin(BaseModel):
    username: str
    password: str

# 返回给前端的用户信息
class UserResponse(BaseModel):
    id: str
    username: str
    # email: str

    class Config:
        from_attributes = True # 允许 Pydantic 读取 SQLAlchemy 模型