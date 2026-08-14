#!/usr/bin/env bash
# 在阿里云轻量 Ubuntu 22.04 上安装 xiaoyeeat-site（需 root）
set -euo pipefail

APP_DIR=/opt/xiaoyeeat-site
REPO=https://github.com/suqijun/xiaoyeeat-site.git

if [[ "$(id -u)" -ne 0 ]]; then
  echo "请用 root 运行（或 sudo bash）"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git python3 python3-venv python3-pip nginx certbot python3-certbot-nginx curl

if [[ -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" pull --ff-only
else
  rm -rf "$APP_DIR"
  git clone "$REPO" "$APP_DIR"
fi

cd "$APP_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "已创建 $APP_DIR/.env —— 请编辑填入 VOLC_APP_ID / VOLC_ACCESS_KEY 后执行: systemctl restart xiaoyeeat"
fi

install -m 644 "$APP_DIR/deploy/xiaoyeeat.service" /etc/systemd/system/xiaoyeeat.service
install -m 644 "$APP_DIR/deploy/nginx-xiaoyeeat.conf" /etc/nginx/sites-available/xiaoyeeat
ln -sf /etc/nginx/sites-available/xiaoyeeat /etc/nginx/sites-enabled/xiaoyeeat
rm -f /etc/nginx/sites-enabled/default

systemctl daemon-reload
systemctl enable --now xiaoyeeat
nginx -t
systemctl reload nginx

echo
echo "==== 安装完成 ===="
systemctl --no-pager --full status xiaoyeeat | head -20
curl -sS http://127.0.0.1:8000/health || true
echo
echo "下一步："
echo "1) nano $APP_DIR/.env  填密钥，然后: systemctl restart xiaoyeeat"
echo "2) DNS: xiaoyeeat.cn / www → 本机公网 IP"
echo "3) certbot --nginx -d xiaoyeeat.cn -d www.xiaoyeeat.cn"
