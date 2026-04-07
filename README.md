# 分布式秒杀系统作业项目

## 项目简介

这是一个基于 `FastAPI + MySQL + Redis + Nginx + Vue 3 + Docker Compose` 实现的分布式秒杀课程作业项目。系统按业务拆分为用户、商品、订单、库存四个微服务，通过 HTTP REST 接口通信，并在统一入口层引入 Nginx，实现容器化部署、反向代理、负载均衡、动静分离与商品详情缓存。

当前项目已经完成基础业务接口，以及课程要求中的容器环境、负载均衡、JMeter 压测、动静分离和 Redis 缓存等内容，并已在商品详情缓存中加入针对缓存穿透、缓存击穿、缓存雪崩的基础防护策略。

## 当前完成情况

- [x] 用户服务：注册、登录、JWT 鉴权
- [x] 商品服务：商品创建、商品列表、商品详情
- [x] 库存服务：库存设置、库存查询、库存锁定、库存确认、库存释放
- [x] 订单服务：创建订单、支付订单、取消订单
- [x] 统一响应结构与基础异常处理
- [x] Dockerfile 与 `docker-compose.yml` 容器化部署
- [x] Nginx 统一网关与反向代理
- [x] 负载均衡实验
- [x] 前端静态资源部署与动静分离
- [x] JMeter 对静态资源和后端接口进行压力测试
- [x] Redis 商品详情页缓存
- [x] 缓存穿透治理
- [x] 缓存击穿治理
- [x] 缓存雪崩治理

## 系统架构

```mermaid
graph LR
    A[Client / Browser / JMeter] --> B[Nginx Gateway]
    B --> C[Vue Frontend Static Files]
    B --> D[User Service]
    B --> E[Product Service]
    B --> F[Order Service]
    B --> G[Inventory Service]
    D --> H[(MySQL)]
    E --> H
    F --> H
    G --> H
    E --> I[(Redis)]
    F --> E
    F --> G
```

## 技术栈

- 后端：`FastAPI`、`SQLAlchemy`、`httpx`
- 数据库：`MySQL 8`
- 缓存：`Redis`
- 网关：`Nginx`
- 前端：`Vue 3`、`Vite`、`Tailwind CSS`
- 容器化：`Docker`、`Docker Compose`
- 压测：`JMeter`

## 服务划分

| 服务 | 说明 | 容器内端口 |
| --- | --- | --- |
| `user_service` | 用户注册、登录、鉴权 | `8001` |
| `product_service` | 商品管理、商品详情、Redis 缓存 | `8002` |
| `order_service` | 下单、支付、取消订单 | `8003` |
| `inventory_service` | 库存设置、查询、锁定、确认、释放 | `8004` |
| `mysql-db` | 持久化存储 | `3306` |
| `flash-redis` | 商品详情缓存 | `6379` |
| `nginx-gateway` | 静态资源分发、API 网关、负载均衡入口 | `80` |

宿主机默认访问入口：

- 前端与统一网关：`http://localhost:8000`
- MySQL：`localhost:3306`
- Redis：`localhost:6379`

## 目录结构

```text
distributed-flash-sale/
├── docker-compose.yml
├── nginx/
│   └── nginx.conf
├── frontend/
├── user_service/
├── product_service/
├── order_service/
├── inventory_service/
├── integration_test.py
└── README.md
```

## 已实现的核心内容

### 1. 基础业务能力

项目目前已经完成以下基础接口：

- 用户：`/api/users/register`、`/api/users/login`
- 商品：`POST /api/products`、`GET /api/products`、`GET /api/products/{product_id}`
- 订单：`POST /api/orders`、`POST /api/orders/{order_id}/pay`、`POST /api/orders/{order_id}/cancel`
- 库存：`POST /api/inventory`、`GET /api/inventory/{product_id}`、`POST /api/inventory/{product_id}/deduct`、`POST /api/inventory/{product_id}/confirm`、`POST /api/inventory/{product_id}/release`

订单流程采用了“先锁库存，再支付确认/取消释放”的思路，适合秒杀场景下的基础演示。

### 2. 容器环境

项目已经配置好多服务的 Docker 相关文件：

- 每个后端服务目录下都提供了 `Dockerfile`
- `frontend/Dockerfile` 使用多阶段构建，先打包 Vue 前端，再交给 Nginx 提供静态资源
- 根目录 `docker-compose.yml` 用于统一拉起 MySQL、Redis、后端服务和 Nginx 网关

当前 Compose 编排包含：

- `mysql-db`
- `flash-redis`
- `user-service`
- `product-service`
- `order-service`
- `inventory-service`
- `nginx-gateway`

说明：

- MySQL 容器启动时会自动创建 `flash_user_db`
- `product_service`、`order_service`、`inventory_service` 启动时会自动检查并创建各自数据库

### 3. 负载均衡

项目通过 Nginx 的 `upstream` 实现反向代理与负载均衡。当前仓库中已经在 `nginx/nginx.conf` 中配置了多个服务的 upstream 池，并将 `/api/*` 请求转发到后端服务。

其中，`product-service` 已作为负载均衡实验对象进行多实例配置预留。默认可采用 Nginx 轮询策略；如需做课程实验对比，也可以在 `upstream` 中切换为以下策略：

- 默认轮询 `round robin`
- 权重轮询 `weight`
- 最少连接 `least_conn`
- IP 绑定 `ip_hash`

### 4. 动静分离

项目已经完成动静分离配置：

- `location /`：由 Nginx 直接返回前端静态资源
- `location /api/users`：转发到用户服务
- `location /api/products`：转发到商品服务
- `location /api/orders`：转发到订单服务
- `location /api/inventory`：转发到库存服务

### 5. 分布式缓存

项目已经在商品服务中引入 Redis，对商品详情接口做了基础缓存与防护治理。

当前缓存逻辑位于 `product_service/api/routes.py`：

- 查询商品详情时，优先读取 Redis
- 缓存命中则直接返回
- 缓存未命中时查询 MySQL
- 查询到数据后写回 Redis
- 缓存 Key 格式：`product:{product_id}`
- 正常商品缓存采用随机过期时间，避免大量 Key 同时失效
- 不存在商品会写入空值缓存，减少恶意不存在请求反复打库
- 商品 ID 会同步到 Redis 索引集合，优先过滤明显非法请求
- 缓存重建时使用 Redis 分布式锁，避免热点 Key 失效瞬间大量并发同时回源

当前实现对应关系：

- 缓存穿透：商品 ID 索引 + 空值缓存
- 缓存击穿：互斥锁 + 等待缓存回填
- 缓存雪崩：缓存 TTL 随机抖动

## JMeter 压测说明

项目已使用 JMeter 对静态资源和后端接口进行压力测试，主要观察以下内容：

- 静态资源访问响应时间
- 后端接口响应时间
- 吞吐量与错误率
- 后端实例的请求分发情况是否大致均衡

建议压测目标：

- 静态资源：`GET http://localhost:8000/`
- 商品列表：`GET http://localhost:8000/api/products`
- 商品详情：`GET http://localhost:8000/api/products/{product_id}`

观察方式：

- 查看 JMeter 的平均响应时间、吞吐量、错误率
- 查看 Nginx 与后端日志，确认请求是否被分发到多个实例

## 统一响应格式

项目中的接口统一返回如下结构：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

## 快速启动

使用 Docker Compose

推荐直接在项目根目录执行：

```bash
docker compose up -d --build
```

如果需要验证商品服务多实例负载均衡：

```bash
docker compose up -d --build --scale product-service=3
```

启动完成后可访问：

- 前端首页：`http://localhost:8000`
- 用户接口：`http://localhost:8000/api/users`
- 商品接口：`http://localhost:8000/api/products`
- 订单接口：`http://localhost:8000/api/orders`
- 库存接口：`http://localhost:8000/api/inventory`

## 可补充的后续工作

- 为负载均衡实验补充更完整的 JMeter 测试报告和截图
- 为热点商品加入更稳健的并发控制与降级机制
- 进一步完善接口文档与自动化测试
