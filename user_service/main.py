from fastapi import FastAPI

app = FastAPI(title="User Service", description="处理用户注册、登录等核心业务")

@app.get("/")
async def root():
    return {"message": "Hello from User Service!", "status": "running"}

@app.get("/api/users/health")
async def health_check():
    return {"status": "ok", "service": "user_service"}

if __name__ == "__main__":
    import uvicorn
    # 宿主机开发时可以用 reload=True 方便热更新
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)