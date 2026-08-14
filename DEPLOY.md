# 公网部署 · 阿里云轻量应用服务器

目标：把 https://github.com/suqijun/xiaoyeeat-site 跑在阿里云轻量上，域名 `xiaoyeeat.cn` 解析过来。  
本站含 **FastAPI + WebSocket**，必须用能跑 Python 的主机（不能只靠静态托管）。

---

## 你需要准备

| 项 | 说明 |
|----|------|
| 轻量实例 | 建议：大陆地域（与备案一致）、≥1 核 2G、系统 **Ubuntu 22.04** |
| 公网 IP | 控制台可见 |
| SSH | 密码或密钥登录 root / ubuntu |
| 防火墙放行 | **80 / 443 / 22**（控制台「防火墙」里加规则） |
| 环境变量 | `VOLC_APP_ID`、`VOLC_ACCESS_KEY`（可选 LLM 三项） |
| 域名 DNS | `xiaoyeeat.cn`、`www` 的 **A 记录** → 轻量公网 IP |

备案：域名已有 `琼ICP备2026010389号-1`。若轻量在**大陆**，接入商需与备案一致或完成接入变更；若暂时用境外轻量，大陆访问可能不稳定，长期仍建议大陆机 + 备案接入。

---

## 一、买 / 开轻量（控制台）

1. 打开 [阿里云轻量应用服务器](https://swas.console.aliyun.com/)
2. 创建实例：镜像选 **Ubuntu 22.04**，套餐按需
3. 记下 **公网 IP**
4. 「防火墙」放行 TCP **22、80、443**

---

## 二、SSH 上去装站点（复制执行）

把下面的 `YOUR_IP` 换成公网 IP：

```bash
ssh root@YOUR_IP
# 若是 ubuntu 用户：ssh ubuntu@YOUR_IP 后再 sudo -i
```

一键安装（推荐）：

```bash
curl -fsSL https://raw.githubusercontent.com/suqijun/xiaoyeeat-site/main/scripts/setup-aliyun.sh | bash
```

或手动：

```bash
apt update && apt install -y git python3 python3-venv python3-pip nginx certbot python3-certbot-nginx
mkdir -p /opt && cd /opt
git clone https://github.com/suqijun/xiaoyeeat-site.git
cd xiaoyeeat-site
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env   # 填入 VOLC_APP_ID / VOLC_ACCESS_KEY 等
```

写入 systemd（若已跑过 setup 脚本可跳过）：

```bash
cp /opt/xiaoyeeat-site/deploy/xiaoyeeat.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now xiaoyeeat
systemctl status xiaoyeeat --no-pager
```

应用只监听本机 **8000**；对外由 Nginx 反代。

---

## 三、Nginx + HTTPS

```bash
cp /opt/xiaoyeeat-site/deploy/nginx-xiaoyeeat.conf /etc/nginx/sites-available/xiaoyeeat
ln -sf /etc/nginx/sites-available/xiaoyeeat /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

DNS 先指到本机后再申请证书：

```bash
certbot --nginx -d xiaoyeeat.cn -d www.xiaoyeeat.cn
```

证书成功后 Nginx 会自动改成 HTTPS。WebSocket 路径 `/ws/` 已在配置里升级。

---

## 四、域名解析

在域名当前 DNS 服务商（腾讯云 / 阿里云 / DNSpod 等）：

| 主机记录 | 类型 | 值 |
|----------|------|-----|
| `@` | A | 轻量公网 IP |
| `www` | A | 轻量公网 IP（或 CNAME 到 `@`） |

若 `daily-menu.xiaoyeeat.cn` 仍走 EdgeOne，**不要改它的记录**，只改主域 `@` / `www`。

解析生效后：

- https://xiaoyeeat.cn/ → 首页  
- /articles/lead-cleaning → 全文  
- /lab → 怎么试 → /lab/call → 接听  
- /health → `"ok": true` 且 `"app_id_set": true`

---

## 五、常用运维

```bash
# 看日志
journalctl -u xiaoyeeat -f

# 改 .env 后重启
systemctl restart xiaoyeeat

# 拉代码更新
cd /opt/xiaoyeeat-site && git pull && .venv/bin/pip install -r requirements.txt && systemctl restart xiaoyeeat
```

---

## 需要我代配时请发

1. 轻量 **公网 IP**  
2. SSH 方式（密码 / 密钥；若用密钥，本机是否已能 `ssh root@IP`）  
3. `.env` 里火山密钥是否已有（本地 `AI客服/.env` 可复用，**不要发到聊天里**，上机后自己粘贴即可）

有 IP 且本机能 SSH 后，可继续由助手远程执行安装与 Nginx 配置。
