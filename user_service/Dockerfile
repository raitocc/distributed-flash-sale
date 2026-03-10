# 1. 基础镜像：选择官方的轻量级 Python 3.10 环境 (slim 版体积更小)
FROM python:3.10-slim

# 2. 设置工作目录：相当于在容器里执行了 cd /app
WORKDIR /app

# 3. 复制依赖清单：先复制 requirements 是一种优化策略，利用 Docker 缓存加速构建
COPY requirements.txt .

# 4. 安装依赖：使用清华源加速安装 (国内服务器必备，虽然你开了代理，但写上更稳)
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 5. 复制源代码：把当前目录下所有的代码拷贝到容器的 /app 目录下
COPY . .

# 6. 暴露端口：声明这个容器内部会使用 8001 端口 (仅仅是声明，方便以后的人看)
EXPOSE 8001

# 7. 启动命令：当容器启动时，执行 uvicorn 启动服务
# 注意：host 必须是 0.0.0.0，否则容器外部无法访问！
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]