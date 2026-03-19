from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import models
import schemas
import database
from core.security import get_password_hash, verify_password, create_access_token
from core.responses import success, ResponseModel

router = APIRouter(prefix="/api/users", tags=["Users"])

@router.post("/register", response_model=ResponseModel[schemas.UserResponse])
def register_user(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    # 1. 检查用户名或邮箱是否已存在
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="用户名已注册")

    # 2. 密码加密并存入数据库
    hashed_password = get_password_hash(user.password)
    new_user = models.User(username=user.username, password_hash=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return success(data=new_user, message="注册成功")

@router.post("/login", response_model=ResponseModel[dict])
def login_user(user: schemas.UserLogin, db: Session = Depends(database.get_db)):
    # 1. 查询用户
    db_user = db.query(models.User).filter(models.User.username == user.username).first()

    # 2. 校验密码
    if not db_user or not verify_password(user.password, db_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    # 3. 生成 JWT Token
    access_token = create_access_token(data={"sub": db_user.username, "user_id": db_user.id})
    return success(data={"access_token": access_token, "token_type": "bearer", "user_id": db_user.id}, message="登录成功")
