#!/bin/bash
# deploy.sh - Ubuntu VPS 一键部署 / 更新脚本
# 首次部署：bash deploy.sh
# 后续更新：git pull && bash deploy.sh
set -e

echo "========================================"
echo "  AI 投研系统 部署脚本 (Ubuntu)"
echo "========================================"

# ── 0. 检测 Python ──────────────────────────────────────────────
if command -v python3.11 &>/dev/null; then
  PYTHON=python3.11
elif command -v python3 &>/dev/null; then
  PYTHON=python3
else
  echo "[错误] 未找到 Python3，请先安装: sudo apt install python3 python3-pip python3-venv"
  exit 1
fi
echo "[OK] Python: $($PYTHON --version)"

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# ── 1. 创建虚拟环境 ─────────────────────────────────────────────
if [ ! -d "venv" ]; then
  echo "[..] 创建虚拟环境..."
  $PYTHON -m venv venv
fi
source venv/bin/activate
echo "[OK] 虚拟环境已激活"

# ── 2. 安装依赖 ─────────────────────────────────────────────────
echo "[..] 安装 Python 依赖..."
pip install -r requirements.txt -q
echo "[OK] 依赖安装完成"

# ── 3. 创建必要目录 ─────────────────────────────────────────────
mkdir -p logs instance
echo "[OK] 目录已就绪 (logs/ instance/)"

# ── 4. 初始化 .env ──────────────────────────────────────────────
if [ ! -f .env ]; then
  echo "[..] 未找到 .env，从模板创建..."
  cp .env.example .env
fi

# 自动生成 SECRET_KEY
if ! grep -q "^SECRET_KEY=" .env 2>/dev/null; then
  SECRET_KEY=$($PYTHON -c "import secrets; print(secrets.token_hex(32))")
  echo "SECRET_KEY=${SECRET_KEY}" >> .env
  echo "[OK] SECRET_KEY 已写入 .env"
else
  echo "[OK] SECRET_KEY 已存在"
fi

# 自动生成 ENCRYPT_KEY（Fernet）
if ! grep -q "^ENCRYPT_KEY=" .env 2>/dev/null; then
  echo "[..] 生成加密密钥..."
  $PYTHON -m utils.crypto
else
  echo "[OK] ENCRYPT_KEY 已存在"
fi

# 保护 .env 文件权限
chmod 600 .env
echo "[OK] .env 权限设置为 600"

# ── 5. 初始化数据库 ─────────────────────────────────────────────
echo "[..] 初始化数据库..."
$PYTHON -c "
from app import app
from models import db
with app.app_context():
    db.create_all()
    print('[OK] 数据库表已就绪')
"

# ── 6. 停止旧进程 ───────────────────────────────────────────────
echo "[..] 停止旧服务..."
systemctl stop ainews 2>/dev/null || pkill -f "gunicorn.*app:app" 2>/dev/null || true
sleep 2

# ── 7. 安装 systemd 服务 ────────────────────────────────────────
SERVICE_FILE="$PROJECT_DIR/systemd/ainews.service"
SYSTEMD_TARGET="/etc/systemd/system/ainews.service"

if [ -f "$SERVICE_FILE" ] && command -v systemctl &>/dev/null; then
  sed "s|/root/AINewsInvest|$PROJECT_DIR|g" "$SERVICE_FILE" > "$SYSTEMD_TARGET"
  systemctl daemon-reload
  systemctl enable ainews
  systemctl start ainews
  echo "[OK] systemd 服务已安装并启动"
else
  echo "[..] 未检测到 systemd，使用 nohup 启动..."
  nohup venv/bin/gunicorn -c gunicorn_conf.py app:app > logs/server.log 2>&1 &
fi

sleep 3

# ── 8. 验证部署 ─────────────────────────────────────────────────
if systemctl is-active --quiet ainews 2>/dev/null || pgrep -f "gunicorn.*app:app" > /dev/null; then
  PUBLIC_IP=$(curl -s --max-time 3 ifconfig.me 2>/dev/null || echo "YOUR_VPS_IP")
  echo ""
  echo "========================================"
  echo "[OK] 部署成功！"
  echo ""
  echo "   访问地址：http://${PUBLIC_IP}:5000"
  echo ""
  echo "   日常维护："
  echo "   查看日志：journalctl -u ainews -f"
  echo "   重启服务：sudo systemctl restart ainews"
  echo "   查看状态：sudo systemctl status ainews"
  echo "========================================"
else
  echo ""
  echo "[错误] 启动失败，查看日志："
  tail -20 logs/server.log 2>/dev/null || echo "(无日志)"
  exit 1
fi
