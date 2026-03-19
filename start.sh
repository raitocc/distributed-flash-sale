#!/bin/bash

echo "[1/3] 开始启动分布式秒杀系统..."

# 1. 启动业务微服务和数据库
echo "正在拉起 MySQL, User Service 和 Product Service..."
docker compose up -d

# 2. "清理旧的监工容器
echo "正在清理历史 Watchtower 容器..."
docker rm -f watchtower 2>/dev/null

# 3. 带着代理配置，重新启动幽灵监工
echo "正在启动 Watchtower 全自动更新守护进程..."
docker run -d \
  --name watchtower \
  -e DOCKER_API_VERSION=1.41 \
  -e HTTP_PROXY="http://192.168.152.1:7890" \
  -e HTTPS_PROXY="http://192.168.152.1:7890" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --interval 30 \
  --cleanup

echo "[完成] 全部微服务启动完毕！"
