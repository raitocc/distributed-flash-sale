# -----------------------------------
# 🔨 第一阶段：编译构建阶段 (Build Stage)
# -----------------------------------
FROM node:20-alpine as build-stage
WORKDIR /app
# 复制 package.json 并使用淘宝镜像加速安装依赖
COPY package*.json ./
RUN npm config set registry https://registry.npmmirror.com/ && npm install
# 复制所有 Vue 源码并打包
COPY . .
RUN npm run build

# -----------------------------------
# 🚀 第二阶段：生产运行阶段 (Production Stage)
# -----------------------------------
FROM nginx:alpine
# 把第一阶段打包生成的 dist 文件夹，复制到 Nginx 的默认静态文件目录
COPY --from=build-stage /app/dist /usr/share/nginx/html
# 暴露 80 端口
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]