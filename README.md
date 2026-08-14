# xiaoyeeat.cn · Works

苏琦珺的 AI 作品站：首页 + 两篇全文 + 线索清洗外呼测试台（可读可试）。

## 本地运行

```bash
cd xiaoyeeat-site
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填写 VOLC_APP_ID / VOLC_ACCESS_KEY（及可选 LLM）
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

打开 http://127.0.0.1:8000/

| 路径 | 内容 |
|------|------|
| `/` | 作品首页 |
| `/articles/lead-cleaning` | 线索清洗全文 |
| `/articles/logistics-sales` | 物流销售全文 |
| `/lab` | 怎么试 |
| `/lab/call` | 外呼测试台（需 `.env` 密钥） |
| `/health` | 密钥是否已配置 |

外呼测试台依赖火山豆包实时语音；未配置密钥时页面可开，通话会报错提示。

## 部署公网

走 **阿里云轻量应用服务器**（详见 [`DEPLOY.md`](./DEPLOY.md)）。

```bash
# 在轻量 Ubuntu 上（root）
curl -fsSL https://raw.githubusercontent.com/suqijun/xiaoyeeat-site/main/scripts/setup-aliyun.sh | bash
# 编辑 /opt/xiaoyeeat-site/.env → systemctl restart xiaoyeeat
# DNS A 记录指到轻量 IP → certbot --nginx -d xiaoyeeat.cn -d www.xiaoyeeat.cn
```

需要能跑 Python + WebSocket；纯静态托管不够。

## 来源

- 首页视觉：`job-search/designs/xiaoyeeat-works`
- 文章：`job-search/文章/...`
- 测试台：`cursor-projects/AI客服`
