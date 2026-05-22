# 🤖 联想百应数字员工

企业级 AI 数字员工管理平台。内置多个场景的数字员工（营销、销售、IT运维等），开箱即用。

## ✨ 功能

- **数字员工商店** — 浏览、选择、启用不同角色的 AI 数字员工
- **智能对话** — 与数字员工对话，流式输出（SSE）
- **技能系统** — 每个数字员工拥有专属技能（文案生成、客户分析等）
- **知识库** — 文档上传 + RAG 检索增强（开发中）
- **本地部署** — 数据物理隔离，不上云

## 🚀 快速开始

```bash
# 1. 安装后端依赖
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. 配置环境变量
cp ../.env.example ../.env
# 编辑 .env，填入 DEEPSEEK_API_KEY

# 3. 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 4. 打开浏览器
# http://localhost:8000
```

## 🔑 演示账号

| 邮箱 | 密码 | 角色 |
|------|------|------|
| admin@lvb.com | admin123 | 管理员 |

## 🧩 技术栈

| 层 | 技术 |
|------|------|
| 前端 | HTML + Alpine.js + TailwindCSS |
| 后端 | Python FastAPI |
| 数据库 | 内存（Demo）/ PostgreSQL（生产） |
| AI | DeepSeek API |

## 📁 项目结构

```
lvb-digital-employee/
├── frontend/
│   └── index.html          # SPA 前端（单文件）
├── backend/
│   ├── app/
│   │   ├── main.py         # FastAPI 入口
│   │   ├── api/            # API 路由
│   │   ├── core/           # 配置、安全
│   │   └── services/       # 业务逻辑
│   └── requirements.txt
├── .env.example
└── docker-compose.yml
```

## 🌐 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/auth/register | 注册 |
| POST | /api/v1/auth/login | 登录 |
| GET | /api/v1/auth/me | 当前用户 |
| GET | /api/v1/employees | 员工列表 |
| POST | /api/v1/chat/send | 对话（SSE 流式） |
