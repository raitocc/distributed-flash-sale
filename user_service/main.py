from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from jose import jwt
import bcrypt

from config import settings
import models
import schemas
import database
from database import engine


# 自动在 MySQL 中建表
models.Base.metadata.create_all(bind=engine)
app = FastAPI(title="User Service - 注册与登录")


# --- 辅助函数 ---
def get_password_hash(password: str) -> str:
    # 生成盐值并哈希
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_password.decode('utf-8')  # 转回字符串存入数据库


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # 校验密码
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    # 使用 settings.secret_key 和 settings.algorithm
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt




# --- API 接口 ---

@app.post("/api/users/register", response_model=schemas.UserResponse)
def register_user(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    # print(f"==== 收到的密码内容: [{user.password}] ====")
    # print(f"==== 收到的密码长度: {len(user.password.encode('utf-8'))} 字节 ====")

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
    return new_user


@app.post("/api/users/login")
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
    return {"access_token": access_token, "token_type": "bearer", "user_id": db_user.id}
