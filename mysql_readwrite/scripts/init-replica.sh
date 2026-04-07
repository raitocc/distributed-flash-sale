#!/bin/bash
set -euo pipefail

# 为什么单独做一个初始化容器，而不是把复制配置写死在主库或从库镜像里：
# 复制关系本质上是“两个已经启动好的 MySQL 实例之间的握手”，
# 它依赖主库和从库都先可连接，再执行 CHANGE REPLICATION SOURCE TO。
# 用一次性初始化容器能把这段“启动后编排逻辑”显式表达出来，答辩时也更好解释。

MASTER_HOST="mysql-master"
SLAVE_HOST="mysql-slave"
ROOT_PASSWORD="95515"
REPL_USER="repl"
REPL_PASSWORD="95515-repl"
PRODUCT_DB="flash_product_db"

echo "[replica-init] 等待主库就绪..."
until mysqladmin ping -h"${MASTER_HOST}" -uroot -p"${ROOT_PASSWORD}" --silent; do
  sleep 2
done

echo "[replica-init] 等待从库就绪..."
until mysqladmin ping -h"${SLAVE_HOST}" -uroot -p"${ROOT_PASSWORD}" --silent; do
  sleep 2
done

echo "[replica-init] 在主库创建复制账号..."
mysql -h"${MASTER_HOST}" -uroot -p"${ROOT_PASSWORD}" <<SQL
CREATE USER IF NOT EXISTS '${REPL_USER}'@'%' IDENTIFIED WITH mysql_native_password BY '${REPL_PASSWORD}';
GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO '${REPL_USER}'@'%';
FLUSH PRIVILEGES;
SQL

echo "[replica-init] 在从库配置复制关系..."
mysql -h"${SLAVE_HOST}" -uroot -p"${ROOT_PASSWORD}" <<SQL
STOP REPLICA;
SET GLOBAL super_read_only = OFF;
SET GLOBAL read_only = OFF;
CREATE DATABASE IF NOT EXISTS \`${PRODUCT_DB}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
SET GLOBAL read_only = ON;
SET GLOBAL super_read_only = ON;
STOP REPLICA;
RESET REPLICA ALL;
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST='${MASTER_HOST}',
  SOURCE_PORT=3306,
  SOURCE_USER='${REPL_USER}',
  SOURCE_PASSWORD='${REPL_PASSWORD}',
  SOURCE_AUTO_POSITION=1,
  GET_SOURCE_PUBLIC_KEY=1;
START REPLICA;
SQL

# 为什么这里打印 SHOW REPLICA STATUS：
# 课程作业里最难讲清楚的不是“写了哪些命令”，而是“复制链路到底有没有真正建立”。
# 把状态信息直接打到容器日志里，后续答辩时能直观看到 IO 线程 / SQL 线程是否正常。
echo "[replica-init] 当前从库复制状态："
mysql -h"${SLAVE_HOST}" -uroot -p"${ROOT_PASSWORD}" -e "SHOW REPLICA STATUS\\G"

echo "[replica-init] 主从复制初始化完成。"
