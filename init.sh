#!/usr/bin/env bash
# 可复现初始化脚本：一键重建并安装「供应链 MVP」（含可直接登录的 admin 账号）
#
# 设计原则：
#   1. 单条命令即可得到一个「能登录」的库 —— 不再有「装完登不进去」的售后补密码步骤。
#   2. 不削弱任何安全机制（如 base.login_cooldown 防暴力破解保持默认）。
#   3. 管理员凭据由模块 post_init_hook 用 Odoo 自身哈希设置，可重复执行。
#
# 用法：
#   ./init.sh                                  # 默认 admin@example.com / admin
#   ADMIN_LOGIN=admin@example.com ADMIN_PASSWORD='YourPass123' ./init.sh
#
set -euo pipefail
cd "$(dirname "$0")"

ADMIN_LOGIN="${ADMIN_LOGIN:-admin@example.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"
DB="${DB_NAME:-supplychain}"

echo "==> [1/4] 停止 odoo 守护进程以释放数据库"
docker compose stop odoo || true

echo "==> [2/4] 删除旧库（若存在）: $DB"
docker compose exec -T db psql -U odoo -d postgres -c "DROP DATABASE IF EXISTS \"$DB\";" || true

echo "==> [3/4] 初始化数据库并安装模块（post_init_hook 会设置 admin 凭据）"
ADMIN_LOGIN="$ADMIN_LOGIN" ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  docker compose run --rm -e ADMIN_LOGIN -e ADMIN_PASSWORD \
  odoo odoo -i supply_chain_demo,sc_ai -d "$DB" --stop-after-init

echo "==> [4/4] 启动 odoo 守护进程"
docker compose up -d odoo

echo "==> 等待服务就绪..."
for i in $(seq 1 40); do
  if curl -fsS "http://localhost:8069/web/login" >/dev/null 2>&1; then
    echo "    odoo 已就绪 (http://localhost:8069)"
    break
  fi
  sleep 2
done

echo
echo "================ 初始化完成 ================"
echo "  访问地址   : http://localhost:8069"
echo "  管理员账号 : $ADMIN_LOGIN"
echo "  管理员密码 : $ADMIN_PASSWORD"
echo "============================================"
