# 🤖 百应智星数字员工

> 企业级 AI 数字员工管理平台。本地部署，数据物理隔离，不上云。

## ✨ 功能

- **5 位数字员工** — 主Agent、项目经理、研发工程师、营销小助手、销售顾问
- **智能对话** — SSE 流式输出，打字机效果
- **JWT 认证** — 安全的登录/注册系统
- **主题切换** — 深色/浅色主题，localStorage 持久化
- **本地部署** — SQLite，数据物理隔离，不上云

## 🎯 数字员工

| ID | 名称 | 角色定位 |
|----|------|----------|
| `primary-agent` | 🧠 主Agent | 战略分析、全局规划、协同调度 |
| `project-manager` | 📋 项目经理 | WBS分解、里程碑、风险管理、敏捷管理 |
| `rd-engineer` | 💻 研发工程师 | 架构设计、代码开发、代码审查、性能优化 |
| `marketing-assistant` | 🤖 营销小助手 | 文案生成、标题优化、竞品分析 |
| `sales-consultant` | 🎯 销售顾问 | 客户话术、需求分析、跟进策略 |

## 🚀 快速开始

```bash
# 1. 进入后端目录
cd backend

# 2. 安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

# 4. 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8081

# 5. 打开浏览器（通过 Nginx 访问）
# http://your-server/        → 百应智星
# http://your-server:8081/   → 直接访问后端
```

## 🔑 演示账号

| 邮箱 | 密码 | 角色 |
|------|------|------|
| admin@lvb.com | admin123 | 管理员 |

## 🌐 Nginx 部署（推荐）

服务端口说明：
- Nginx 监听 `0.0.0.0:8000`
- `/` → 百应智星后端 `127.0.0.1:8081`
- `/bg/` → bg-eraser 后端 `127.0.0.1:8082`

```nginx
# /etc/nginx/sites-available/lvb-digit
server {
    listen 8000;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }

    location /bg/ {
        rewrite ^/bg(/.*)$ $1 break;
        proxy_pass http://127.0.0.1:8082;
        proxy_buffering off;
    }
}
```

## 🛠 systemd 服务管理

```bash
# 重启服务
sudo systemctl restart lvb-digital-employee

# 查看状态
sudo systemctl status lvb-digital-employee

# 查看日志
sudo journalctl -u lvb-digital-employee -f
```

## 🔌 API 接口

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/v1/auth/register` | 注册用户 | ❌ |
| POST | `/api/v1/auth/login` | 登录 | ❌ |
| GET | `/api/v1/auth/me` | 当前用户信息 | ✅ |
| GET | `/api/v1/employees` | 数字员工列表 | ❌ |
| GET | `/api/v1/employees/{id}` | 员工详情 | ❌ |
| POST | `/api/v1/chat/send` | 发送消息（SSE流式） | ✅ |
| GET | `/api/v1/chat/history` | 对话历史 | ✅ |
| GET | `/api/health` | 健康检查 | ❌ |

### 对话 API 示例

```bash
# 1. 登录获取 Token
TOKEN=$(curl -s -X POST http://localhost:8081/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@lvb.com","password":"admin123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. 获取数字员工列表
curl http://localhost:8081/api/v1/employees \
  -H "Authorization: Bearer $TOKEN"

# 3. 发送对话（SSE流式）
curl -N -X POST http://localhost:8081/api/v1/chat/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"employee_id":"primary-agent","message":"你好"}'
```

## 🧩 技术栈

| 层 | 技术 |
|----|------|
| 前端 | HTML + Alpine.js + TailwindCSS |
| 后端 | Python FastAPI + uvicorn |
| 数据库 | SQLite（本地）+ 内存模拟 |
| AI | DeepSeek V4 Flash（`deepseek-v4-flash`） |
| 部署 | Nginx + systemd |
| 协议 | SSE（Server-Sent Events）流式输出 |

## 📁 项目结构

```
lvb-digital-employee/
├── frontend/
│   └── index.html              # SPA 前端（深浅主题、Nginx路径分流）
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 入口 + CORS
│   │   ├── api/v1/            # API 路由
│   │   │   ├── auth.py        # JWT 认证（注册/登录/me）
│   │   │   ├── employees.py    # 数字员工 CRUD
│   │   │   └── chat.py        # SSE 流式对话
│   │   ├── core/              # 配置、安全、JWT
│   │   ├── models/            # Pydantic 模型
│   │   ├── schemas/            # API 请求/响应 schemas
│   │   └── services/           # AI 服务 + 内存数据库
│   ├── .env                    # 环境变量（API Key 等）
│   ├── .env.example            # 环境变量模板
│   └── requirements.txt
├── deploy/
│   ├── nginx.conf             # Nginx 配置
│   └── systemd.conf            # systemd 服务模板
├── docker-compose.yml          # Docker 部署（可选）
├── Dockerfile
└── README.md
```

## ⚙️ 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | 必填 |
| `DEEPSEEK_MODEL` | 模型名称 | `deepseek-v4-flash` |
| `SECRET_KEY` | JWT 签名密钥 | 生产环境请修改 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token 过期时间（分钟） | `10080`（7天） |
