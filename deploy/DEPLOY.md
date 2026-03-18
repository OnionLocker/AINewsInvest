# Alpha Vault 生产部署指南

## 1. 环境准备

```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv nginx
```

## 2. 项目部署

```bash
sudo mkdir -p /opt/alphavault
sudo chown www-data:www-data /opt/alphavault
cd /opt/alphavault

# 拉取代码
git clone <repo-url> .

# Python 虚拟环境
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn

# 初始化
mkdir -p logs data
python scripts/build_symbol_db.py
```

## 3. 配置

```bash
cp .env.example .env
# 编辑 .env，配置数据库、SECRET_KEY、LLM API 等
```

## 4. Systemd 服务

```bash
sudo cp deploy/alphavault.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable alphavault
sudo systemctl start alphavault
sudo systemctl status alphavault
```

## 5. Nginx 反向代理

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/alphavault
sudo ln -sf /etc/nginx/sites-available/alphavault /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## 6. 健康检查

```bash
curl http://localhost/api/health
# 应返回 {"status": "ok", ...}
```

## 7. 日志查看

```bash
sudo journalctl -u alphavault -f       # systemd 日志
tail -f /opt/alphavault/logs/app.log    # 应用日志
```

## 8. 更新部署

```bash
cd /opt/alphavault
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart alphavault
```
