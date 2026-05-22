# 数字员工 · CEO行业专家助手 · 技术架构文档
## Technical Architecture Document v1.0

> **项目代号：** 智闻（ZhiWen）
> **版本：** v1.0
> **日期：** 2025-05-22
> **状态：** 初始版本

---

## 一、系统架构总览

### 1.1 架构原则

```
1. 模块化自治     — 每个模块独立部署、独立扩展
2. 事件驱动       — 模块间通过消息队列解耦
3. 向量检索优先   — 长期记忆基于pgvector语义搜索
4. 可插拔采集器   — 新增数据源无需修改核心代码
5. 最小依赖       — 优先使用轻量级组件，降低运维复杂度
```

### 1.2 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户交互层                                       │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│   │   飞书Bot     │  │   Web管理后台  │  │   H5/小程序   │  │  开放API     │  │
│   │  （消息/文档） │  │  （配置/查看） │  │  （手机端）  │  │  （第三方）  │  │
│   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
└──────────┼──────────────────┼──────────────────┼──────────────────┼──────────┘
           │                  │                  │                  │
┌──────────▼──────────────────▼──────────────────▼──────────────────▼──────────┐
│                              API网关层（NGINX/FastAPI）                        │
│         Authentication / Rate Limiting / Load Balancing / SSL Termination    │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────────┐
│                              应用服务层（FastAPI）                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                        Router Layer（路由层）                            │  │
│  │  /api/v1/auth  /api/v1/topics  /api/v1/reports  /api/v1/analysis       │  │
│  │  /api/v1/memory  /api/v1/feishu  /api/v1/collection  /api/v1/push     │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │  Topic Svc  │ │  Report Svc │ │  Memory Svc │ │  Analysis Svc│          │
│  │  主题配置    │ │  报告生成   │ │  记忆管理    │ │  AI分析     │          │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │ Collection  │ │  Push Svc   │ │  Feishu Svc │ │  Crawler Mgmt│          │
│  │  采集管理    │ │  推送服务   │ │  飞书集成   │ │  爬虫管理    │          │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘          │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
         ┌──────────────────────────┼──────────────────────────┐
         │                          │                          │
         ▼                          ▼                          ▼
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  Message Queue  │      │   AI Model Hub  │      │   Task Scheduler │
│  （Redis Streams）│      │  （DeepSeek API）│      │  （APScheduler）  │
└────────┬────────┘      └────────┬────────┘      └────────┬────────┘
         │                          │                          │
         ▼                          ▼                          ▼
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  Data Collectors│      │  Vector Search  │      │   Report Gen    │
│  爬虫/订阅/RSS   │      │  （pgvector）    │      │   报告生成       │
└────────┬────────┘      └────────┬────────┘      └────────┬────────┘
         │                          │                          │
         └──────────────────────────┼──────────────────────────┘
                                    │
┌──────────────────────────────────▼───────────────────────────────────────────┐
│                              数据持久层                                        │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────────┐ │
│  │  PostgreSQL      │  │  Redis            │  │  File Storage（MinIO/S3）   │ │
│  │  主库+pgvector   │  │  缓存+队列+会话   │  │  报告/截图/图片/PDF         │ │
│  │  用户/主题/报告   │  │  临时数据         │  │  HTML模板                   │ │
│  └──────────────────┘  └──────────────────┘  └──────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              外部依赖层                                       │
│  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐ ┌──────────────┐  │
│  │  DeepSeek API  │ │  飞书开放平台   │ │  新闻源/RSS    │ │  第三方API   │  │
│  │  AI分析/生成   │ │  消息/文档/日历 │ │  公开数据      │ │  数据采集    │  │
│  └────────────────┘ └────────────────┘ └────────────────┘ └──────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、技术选型

### 2.1 技术栈总表

| 层级 | 组件 | 技术选型 | 说明 |
|------|------|---------|------|
| **API框架** | 后端框架 | FastAPI + Uvicorn | 高性能异步ASGI |
| **前端** | 管理后台 | React + Ant Design + TailwindCSS | 企业级UI |
| **前端** | H5端 | Vue3 + Vant | 移动端适配 |
| **数据库** | 主库 | PostgreSQL 16 + pgvector | 向量存储+关系数据 |
| **数据库** | 缓存 | Redis 7 | 缓存+队列+会话 |
| **文件存储** | 对象存储 | MinIO（本地）/ S3（云上） | 报告/图片存储 |
| **AI模型** | LLM | DeepSeek V4 Flash | 分析+摘要+生成 |
| **任务调度** | 定时任务 | APScheduler | 定时采集+推送 |
| **消息队列** | 异步队列 | Redis Streams | 爬虫任务+报告生成队列 |
| **爬虫** | HTTP | httpx + Playwright | 异步HTTP+JS渲染 |
| **爬虫** | RSS | feedparser | RSS/Atom订阅 |
| **爬虫** | 爬虫框架 | Scrapy（可选） | 复杂站点 |
| **邮件** | SMTP | smtplib / Mailgun | 告警通知 |
| **飞书** | SDK | lark-oapi | 消息+文档+日历 |
| **部署** | 容器 | Docker + Docker Compose | 本地开发+部署 |
| **部署** | K8s | Kubernetes（可选） | 生产扩展 |
| **反向代理** | 网关 | NGINX | SSL+负载均衡 |
| **监控** | 日志 | Structured JSON Logs | 日志收集分析 |

### 2.2 为什么这样选

```
PostgreSQL + pgvector：
  ✅ 一套数据库同时管理关系数据+向量数据
  ✅ pgvector性能接近专用向量数据库（Milvus/Pinecone）
  ✅ 运维复杂度低，1台DB解决
  ❌ 亿级向量时需要分片（但初期绝对够用）

Redis Streams vs RabbitMQ：
  ✅ Redis已有，零新增组件
  ✅ 支持消费组，天然支持多Worker并发消费
  ✅ 支持持久化（disk）+ ACK机制
  ❌ 功能比Kafka弱，但对我们的场景足够

DeepSeek V4 Flash：
  ✅ 成本低（$0.1/1M tokens）
  ✅ 速度极快（Flash注意力）
  ✅ 中文理解优秀
  ✅ 128K上下文（长报告无压力）

MinIO vs 云存储：
  ✅ 完全兼容S3 API，未来可无缝迁移到阿里云OSS/腾讯云COS
  ✅ 本地开发无需付费
  ✅ 单机部署足够，高可用按需升级
```

---

## 三、数据库设计

### 3.1 ER图

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│    User      │       │ Organization │       │  NewsSource  │
├──────────────┤       ├──────────────┤       ├──────────────┤
│ id (PK)      │       │ id (PK)       │       │ id (PK)       │
│ username     │       │ name          │       │ name          │
│ email        │       │ industry      │       │ url           │
│ phone        │       │ created_at    │       │ type (RSS/API)│
│ role         │       └───────┬───────┘       │ update_freq   │
│ org_id (FK)  │               │               │ is_active     │
│ created_at   │               │ 1:N           │ last_fetch    │
└───────┬──────┘               │               └───────────────┘
        │                      │
        │ 1:N                  │ 1:N
        ▼                      ▼
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│   Topic      │       │    Report    │       │  RawArticle  │
├──────────────┤       ├──────────────┤       ├──────────────┤
│ id (PK)      │       │ id (PK)       │       │ id (PK)       │
│ name         │       │ topic_id (FK) │       │ source_id(FK)│
│ keywords     │       │ title         │       │ url           │
│ exclude_kw   │       │ content       │       │ title         │
│ category     │       │ summary       │       │ content       │
│ push_cycle   │       │ ai_analysis   │       │ published_at  │
│ is_active    │       │ swot_json     │       │ fetched_at    │
│ org_id (FK)  │       │ risk_level    │       │ vector_emb    │
│ user_id (FK) │       │ push_time     │       │ topic_ids     │
│ created_at   │       │ status        │       │ is_processed  │
└───────┬──────┘       │ report_type   │       └───────┬───────┘
        │              │ created_at    │               │
        │ 1:N          └───────┬───────┘               │ N:M
        ▼                      │ 1:N                   ▼
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│  TopicSource │       │ ReportItem   │       │   Memory     │
├──────────────┤       ├──────────────┤       ├──────────────┤
│ id (PK)      │       │ id (PK)       │       │ id (PK)       │
│ topic_id(FK) │       │ report_id(FK) │       │ org_id (FK)   │
│ source_id(FK)│       │ article_id(FK)│       │ user_id (FK)  │
│ weight       │       │ importance   │       │ memory_type  │
└──────────────┘       │ source_conf  │       │ content       │
                       │ created_at    │       │ embedding     │
                       └───────────────┘       │ created_at    │
                                               │ updated_at    │
                                               │ importance    │
                                               └───────────────┘

┌──────────────┐       ┌──────────────┐
│   UserPref    │       │  PushRecord  │
├──────────────┤       ├──────────────┤
│ id (PK)       │       │ id (PK)       │
│ user_id (FK)  │       │ report_id(FK) │
│ pref_key      │       │ channel      │
│ pref_value    │       │ sent_at      │
│ updated_at    │       │ status       │
└──────────────┘       │ error_msg    │
                       └──────────────┘
```

### 3.2 核心表结构

#### users（用户表）
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(20),
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'user',  -- admin/manager/user
    org_id UUID REFERENCES organizations(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_users_org ON users(org_id);
CREATE INDEX idx_users_email ON users(email);
```

#### organizations（组织表）
```sql
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    industry VARCHAR(50),
    scale VARCHAR(20),  -- small/medium/large
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### topics（主题配置表）
```sql
CREATE TABLE topics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),  -- 创建者
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,  -- A/B/C/D/E 分类
    keywords TEXT[] NOT NULL,  -- 关键词数组
    exclude_keywords TEXT[],  -- 排除词
    push_cycle VARCHAR(20) DEFAULT 'daily',  -- daily/weekly/monthly
    push_time TIME DEFAULT '08:30:00',  -- 推送时间
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_topics_org ON topics(org_id);
CREATE INDEX idx_topics_active ON topics(is_active) WHERE is_active = TRUE;
```

#### news_sources（新闻源表）
```sql
CREATE TABLE news_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    source_type VARCHAR(20) NOT NULL,  -- rss/api/crawl
    url TEXT NOT NULL,
    update_freq VARCHAR(20) DEFAULT '1h',  -- 更新频率
    is_active BOOLEAN DEFAULT TRUE,
    last_fetch_at TIMESTAMP,
    last_fetch_status VARCHAR(20),  -- success/failed
    config JSONB,  -- 额外配置（headers/auth等）
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_news_sources_active ON news_sources(is_active);
```

#### topic_sources（主题-新闻源关联表）
```sql
CREATE TABLE topic_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID REFERENCES topics(id) ON DELETE CASCADE,
    source_id UUID REFERENCES news_sources(id) ON DELETE CASCADE,
    weight FLOAT DEFAULT 1.0,  -- 权重（影响重要性评分）
    UNIQUE(topic_id, source_id)
);
```

#### raw_articles（原始文章表）
```sql
CREATE TABLE raw_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES news_sources(id),
    url TEXT NOT NULL,
    title VARCHAR(500) NOT NULL,
    content TEXT,  -- 全文（可能为空，等解析）
    summary TEXT,  -- AI生成的摘要
    published_at TIMESTAMP,  -- 文章发布时间
    fetched_at TIMESTAMP DEFAULT NOW(),
    vector_embedding VECTOR(1536),  -- DeepSeek embedding
    language VARCHAR(10) DEFAULT 'zh',
    is_processed BOOLEAN DEFAULT FALSE,
    duplicate_of UUID REFERENCES raw_articles(id),  -- 去重引用
    metadata JSONB  -- 额外信息（作者/图片/标签等）
);

CREATE INDEX idx_raw_articles_source ON raw_articles(source_id);
CREATE INDEX idx_raw_articles_published ON raw_articles(published_at DESC);
CREATE INDEX idx_raw_articles_processed ON raw_articles(is_processed) WHERE is_processed = FALSE;
-- 向量索引
CREATE INDEX idx_raw_articles_emb ON raw_articles USING ivfflat (vector_embedding vector_cosine_ops);
```

#### reports（报告表）
```sql
CREATE TABLE reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID REFERENCES topics(id) ON DELETE CASCADE,
    report_type VARCHAR(20) NOT NULL,  -- daily/weekly/monthly/quarterly/yearly
    title VARCHAR(300) NOT NULL,
    summary TEXT,  -- 执行摘要
    content JSONB,  -- 报告正文（结构化JSON）
    swot JSONB,  -- SWOT分析结果
    risk_level VARCHAR(10),  -- high/medium/low
    risk_items JSONB,  -- 风险项列表
    opportunities JSONB,  -- 机会建议
    push_time TIMESTAMP,
    status VARCHAR(20) DEFAULT 'draft',  -- draft/generating/pushed/failed
    feishu_doc_token VARCHAR(100),  -- 飞书文档token
    feishu_msg_id VARCHAR(100),  -- 飞书消息ID
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_reports_topic ON reports(topic_id);
CREATE INDEX idx_reports_type ON reports(report_type);
CREATE INDEX idx_reports_created ON reports(created_at DESC);
```

#### report_items（报告条目表）
```sql
CREATE TABLE report_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID REFERENCES reports(id) ON DELETE CASCADE,
    article_id UUID REFERENCES raw_articles(id),
    title VARCHAR(300),
    summary TEXT,
    importance FLOAT DEFAULT 0.5,  -- 0-1 重要性评分
    source_confidence FLOAT DEFAULT 0.5,  -- 来源置信度
    is_key_event BOOLEAN DEFAULT FALSE,  -- 是否重大事件
    tag VARCHAR(50),  -- 标签（政策/融资/技术等）
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_report_items_report ON report_items(report_id);
```

#### memories（记忆表）
```sql
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),  -- 可为空（组织级记忆）
    memory_type VARCHAR(30) NOT NULL,  -- ceo_profile/org_profile/topic_tracking/conversation
    content TEXT NOT NULL,
    embedding VECTOR(1536),  -- 向量表示
    importance FLOAT DEFAULT 0.5,
    source VARCHAR(50),  -- 来源：report/manual/ai_inference
    source_id UUID,  -- 来源ID（报告ID等）
    tags TEXT[],  -- 标签
    is_active BOOLEAN DEFAULT TRUE,
    last_accessed_at TIMESTAMP,
    access_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_memories_org ON memories(org_id);
CREATE INDEX idx_memories_type ON memories(memory_type);
CREATE INDEX idx_memories_emb ON memories USING ivfflat (embedding vector_cosine_ops);
-- 重要记忆优先召回
CREATE INDEX idx_memories_importance ON memories(importance DESC) WHERE is_active = TRUE;
```

#### push_records（推送记录表）
```sql
CREATE TABLE push_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID REFERENCES reports(id),
    channel VARCHAR(20) NOT NULL,  -- feishu/email/webhook
    recipient VARCHAR(100),  -- 飞书open_id/邮箱等
    status VARCHAR(20) DEFAULT 'pending',  -- pending/sent/failed
    sent_at TIMESTAMP,
    error_msg TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_push_records_report ON push_records(report_id);
CREATE INDEX idx_push_records_status ON push_records(status);
```

### 3.3 pgvector 向量检索配置

```sql
-- 启用pgvector扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 向量维度（DeepSeek embedding dimension）
-- 注意：不同模型维度不同，需与实际使用模型匹配

-- 近似搜索示例
SELECT id, content, 1 - (embedding <=> $query_embedding) AS similarity
FROM memories
WHERE org_id = $org_id
  AND memory_type = 'topic_tracking'
  AND is_active = TRUE
ORDER BY embedding <=> $query_embedding
LIMIT 5;
```

---

## 四、API设计

### 4.1 API路由总览

```
/api/v1/
├── auth/
│   ├── POST   /login              # 登录
│   ├── POST   /register           # 注册
│   ├── POST   /refresh            # 刷新Token
│   └── POST   /logout             # 登出
│
├── users/
│   ├── GET    /me                  # 当前用户信息
│   ├── PUT    /me                  # 更新个人信息
│   ├── GET    /                    # 用户列表（管理员）
│   └── DELETE /{id}                # 删除用户（管理员）
│
├── organizations/
│   ├── GET    /                    # 组织列表
│   ├── POST   /                    # 创建组织
│   ├── GET    /{id}                # 组织详情
│   └── PUT    /{id}                # 更新组织
│
├── topics/
│   ├── GET    /                    # 主题列表
│   ├── POST   /                    # 创建主题
│   ├── GET    /{id}                # 主题详情
│   ├── PUT    /{id}                # 更新主题
│   ├── DELETE /{id}                # 删除主题
│   └── POST   /{id}/sources        # 关联新闻源
│
├── sources/
│   ├── GET    /                    # 新闻源列表
│   ├── POST   /                    # 添加新闻源
│   ├── GET    /{id}                # 新闻源详情
│   ├── PUT    /{id}                # 更新新闻源
│   ├── DELETE /{id}                # 删除新闻源
│   └── POST   /{id}/test           # 测试连接
│
├── reports/
│   ├── GET    /                    # 报告列表
│   ├── POST   /generate            # 手动生成报告
│   ├── GET    /{id}                # 报告详情
│   ├── GET    /{id}/items          # 报告条目列表
│   ├── GET    /{id}/download       # 下载报告（HTML/PDF）
│   └── DELETE /{id}                # 删除报告
│
├── analysis/
│   ├── POST   /cross-validate      # 交叉验证分析
│   ├── POST   /swot                # SWOT分析
│   ├── POST   /risk-assess         # 风险评估
│   └── POST   /opportunity         # 机会识别
│
├── memory/
│   ├── GET    /                    # 记忆列表
│   ├── POST   /                    # 添加记忆
│   ├── GET    /profile             # CEO画像
│   ├── GET    /search              # 记忆检索
│   ├── PUT    /{id}                # 更新记忆
│   ├── DELETE /{id}                # 删除记忆
│   └── POST   /clear               # 清除记忆
│
├── collection/
│   ├── POST   /trigger             # 手动触发采集
│   ├── GET    /status              # 采集状态
│   └── GET    /articles            # 原始文章列表
│
├── push/
│   ├── GET    /settings            # 推送设置
│   ├── PUT    /settings            # 更新推送设置
│   ├── POST   /test                # 测试推送
│   └── GET    /records             # 推送记录
│
└── feishu/
    ├── GET    /auth                # 飞书授权
    ├── POST   /callback            # 飞书回调
    ├── GET    /documents           # 飞书文档列表
    └── POST   /documents           # 创建飞书文档
```

### 4.2 核心API详细设计

#### 4.2.1 报告生成 API

```yaml
POST /api/v1/reports/generate
Description: 手动触发报告生成
Request:
  {
    "topic_id": "uuid",           # 必填：主题ID
    "report_type": "daily",       # daily/weekly/monthly/quarterly/yearly
    "force_refresh": false,       # 是否强制重新采集
    "push_now": true             # 生成后立即推送
  }
Response:
  {
    "code": 0,
    "message": "报告生成任务已创建",
    "data": {
      "report_id": "uuid",
      "task_id": "uuid",         # 用于查询进度
      "estimated_time": 120      # 预计秒数
    }
  }
```

#### 4.2.2 记忆检索 API

```yaml
GET /api/v1/memory/search
Description: 基于语义的记忆检索
Query:
  - q: "搜索query" (必填)
  - memory_type: "ceo_profile|org_profile|topic_tracking|conversation" (可选)
  - limit: 10 (可选，默认10)
  - threshold: 0.7 (可选，默认0.7相似度阈值)
Response:
  {
    "code": 0,
    "data": {
      "results": [
        {
          "id": "uuid",
          "content": "记忆内容...",
          "memory_type": "topic_tracking",
          "importance": 0.85,
          "similarity": 0.92,
          "tags": ["原材料", "成本"],
          "created_at": "2025-05-20T10:00:00Z"
        }
      ],
      "total": 5
    }
  }
```

#### 4.2.3 CEO画像 API

```yaml
GET /api/v1/memory/profile
Description: 获取CEO画像（阅读偏好/沟通习惯/追踪主题）
Response:
  {
    "code": 0,
    "data": {
      "completeness": 0.78,       # 画像完整度
      "preferences": {
        "reading_depth": "detailed",  # 详细/简洁
        "push_time": "08:30",
        "favorite_sections": ["风险预警", "机会建议"],
        "communication_style": "concise"
      },
      "tracking_topics": [
        {
          "topic_id": "uuid",
          "name": "原材料价格",
          "tracking_days": 127,
          "data_points": 87,
          "trend": "up",
          "last_value": "+15.3%"
        }
      ],
      "key_memories": [
        {
          "id": "uuid",
          "content": "张总关注化工原材料成本变化...",
          "type": "preference",
          "confidence": 0.9
        }
      ],
      "ai_insights": [
        "观察到张总每周一喜欢看深度分析报告",
        "倾向于先看风险再看机会"
      ]
    }
  }
```

#### 4.2.4 深度分析 API

```yaml
POST /api/v1/analysis/cross-validate
Description: 多源交叉验证分析
Request:
  {
    "article_ids": ["uuid1", "uuid2", "uuid3"],
    "claim": "原油价格将持续上涨"
  }
Response:
  {
    "code": 0,
    "data": {
      "claim": "原油价格将持续上涨",
      "confidence": "high",           # high/medium/low
      "supporting_sources": [
        {
          "article_id": "uuid1",
          "source": "Bloomberg",
          "evidence": "OPEC+维持减产决议至Q3",
          "reliability": 0.95
        }
      ],
      "contradicting_sources": [],
      "ai_inference": {
        "reasoning": "基于历史数据+当前供需分析...",
        "probability": 0.78,
        "time_horizon": "3-6个月"
      },
      "verdict": "✅ 高置信度：多个独立来源交叉验证一致"
    }
  }
```

---

## 五、核心服务设计

### 5.1 服务架构

```
app/
├── api/v1/
│   ├── auth.py           # 认证路由
│   ├── users.py          # 用户路由
│   ├── topics.py         # 主题路由
│   ├── sources.py        # 新闻源路由
│   ├── reports.py        # 报告路由
│   ├── analysis.py       # 分析路由
│   ├── memory.py         # 记忆路由
│   ├── collection.py     # 采集路由
│   ├── push.py           # 推送路由
│   └── feishu.py         # 飞书路由
│
├── core/
│   ├── config.py         # 配置管理
│   ├── security.py       # 安全（JWT/加密）
│   ├── database.py        # 数据库连接
│   └── deps.py           # 依赖注入
│
├── models/               # SQLAlchemy模型
│   ├── user.py
│   ├── topic.py
│   ├── source.py
│   ├── article.py
│   ├── report.py
│   └── memory.py
│
├── schemas/              # Pydantic schemas
│   ├── user.py
│   ├── topic.py
│   ├── report.py
│   └── memory.py
│
├── services/
│   ├── auth.py           # 认证服务
│   ├── ai.py             # AI服务（DeepSeek）
│   ├── crawler.py        # 爬虫服务
│   ├── rss.py            # RSS服务
│   ├── report.py         # 报告生成服务
│   ├── analysis.py       # 分析服务
│   ├── memory.py         # 记忆服务
│   ├── push.py           # 推送服务
│   ├── feishu.py         # 飞书服务
│   └── vector.py         # 向量服务（pgvector）
│
├── tasks/
│   ├── scheduler.py      # 定时任务调度器
│   ├── collectors.py     # 采集任务
│   ├── report_generator.py # 报告生成任务
│   └── push_worker.py    # 推送worker
│
└── utils/
    ├── embedding.py      # 向量嵌入工具
    ├── text_processor.py # 文本处理工具
    └── logger.py         # 日志工具
```

### 5.2 服务依赖关系

```
用户请求
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI (Uvicorn ASGI)                     │
└───────────────────────────────┬─────────────────────────────────┘
                                │
    ┌───────────────────────────┼───────────────────────────┐
    │                           │                           │
    ▼                           ▼                           ▼
┌─────────┐              ┌─────────┐                ┌─────────┐
│ Auth Svc│              │ Topic Svc│                │ Report Svc│
│ 认证服务│              │ 主题服务 │                │ 报告服务 │
└────┬────┘              └────┬────┘                └────┬────┘
     │                        │                           │
     │                        ▼                           ▼
     │                 ┌─────────────┐            ┌─────────────┐
     │                 │  Crawler Svc │            │  AI Svc     │
     │                 │  爬虫服务    │            │ DeepSeek    │
     │                 └──────┬──────┘            └──────┬──────┘
     │                         │                          │
     │     ┌───────────────────┴───────────────────┐     │
     │     │                                       │     │
     │     ▼                                       ▼     │
     │ ┌─────────┐                          ┌─────────────┐ │
     │ │RSS Fetch│                          │ Vector Svc  │ │
     │ │HTTP Get │                          │ pgvector    │ │
     │ └────┬────┘                          └──────┬──────┘ │
     │      │                                      │        │
     │      ▼                                      │        │
     │ ┌─────────┐                                   │        │
     │ │Article  │                                   │        │
     │ │Parser   │                                   │        │
     │ └────┬────┘                                   │        │
     │      │                                        │        │
     │      └────────────┬───────────────────────────┘        │
     │                   │                                      │
     │                   ▼                                      │
     │            ┌─────────────┐                               │
     │            │  PostgreSQL │                               │
     │            │  + pgvector  │                               │
     │            └─────────────┘                               │
     │                                                             │
     │     ┌────────────────────────────────────┐                │
     │     │         Redis Streams               │                │
     │     │  异步队列：采集任务/报告生成/推送    │                │
     │     └────────────┬────────────────────────┘                │
     │                  │                                          │
     │     ┌────────────┼────────────────────────┐                 │
     │     ▼            ▼                        ▼                 │
     │ ┌─────────┐ ┌─────────────┐        ┌─────────────┐          │
     │ │Collector│ │Report Worker│        │ Push Worker │          │
     │ │ Worker  │ │  报告生成    │        │  推送发送   │          │
     │ └─────────┘ └─────────────┘        └─────────────┘          │
     │                                                           │
     └───────────────────────────────────────────────────────────┘

                                    │
                                    ▼
                          ┌─────────────────┐
                          │   飞书开放平台    │
                          │  消息/文档/日历   │
                          └─────────────────┘
```

### 5.3 关键服务设计

#### 5.3.1 AI服务（ai.py）

```python
# 服务职责：
# 1. 摘要生成
# 2. SWOT分析
# 3. 风险评估
# 4. 机会识别
# 5. 向量嵌入
# 6. 记忆检索

from app.services.ai import AIService

ai_service = AIService()

# 摘要生成
summary = await ai_service.generate_summary(
    texts=["文章1内容...", "文章2内容..."],
    max_length=500
)

# SWOT分析
swot = await ai_service.analyze_swot(
    topic="化工原材料价格上涨",
    articles=[article1, article2, article3]
)
# 返回: {"strengths": [...], "weaknesses": [...], "opportunities": [...], "threats": [...]}

# 风险评估
risk = await ai_service.assess_risk(
    topic="原材料价格",
    articles=[...],
    historical_data=[...]
)
# 返回: {"level": "high", "items": [...], "probability": 0.85}

# 记忆检索（向量相似度）
memories = await ai_service.search_memory(
    query="CEO关注哪些成本指标",
    org_id=org_uuid,
    limit=5,
    memory_type="ceo_profile"
)

# CEO画像更新
profile = await ai_service.update_ceo_profile(
    user_id=user_uuid,
    interaction_data={"reading_time": 300, "clicked_items": [...]}
)
```

#### 5.3.2 爬虫服务（crawler.py）

```python
# 服务职责：
# 1. HTTP爬虫（httpx异步）
# 2. RSS订阅（feedparser）
# 3. Playwright渲染（JS页面）
# 4. 文章解析（标题/正文/发布时间）

from app.services.crawler import CrawlerService

crawler = CrawlerService()

# 添加任务到队列
await crawler.queue_task(
    source_id=source_uuid,
    url="https://example.com/news",
    priority=1  # 1=高 2=中 3=低
)

# 手动触发采集
result = await crawler.fetch_article(
    url="https://news.example.com/article/123",
    source_type="web"
)
# 返回: {"title": "...", "content": "...", "published_at": datetime}

# RSS订阅采集
items = await crawler.fetch_rss(
    rss_url="https://example.com/feed.xml"
)
# 返回: [{"title": "...", "url": "...", "published_at": datetime}, ...]
```

#### 5.3.3 报告生成服务（report.py）

```python
# 服务职责：
# 1. 多源文章聚合
# 2. 去重+重要性排序
# 3. AI摘要生成
# 4. SWOT分析
# 5. 风险/机会识别
# 6. HTML/飞书文档生成

from app.services.report import ReportService

report_service = ReportService()

# 生成报告
report = await report_service.generate(
    topic_id=topic_uuid,
    report_type="daily",
    date_range=(start_date, end_date)
)

# 报告状态
status = await report_service.get_status(report_id)

# 下载报告
html_content = await report_service.export_html(report_id)
pdf_buffer = await report_service.export_pdf(report_id)
```

#### 5.3.4 记忆服务（memory.py）

```python
# 服务职责：
# 1. 记忆存储（PostgreSQL + pgvector）
# 2. 记忆检索（向量相似度搜索）
# 3. CEO画像管理
# 4. 企业档案管理
# 5. 话题追踪数据

from app.services.memory import MemoryService

memory = MemoryService()

# 添加记忆
mem = await memory.add(
    org_id=org_uuid,
    user_id=user_uuid,
    memory_type="topic_tracking",
    content="原材料价格已追踪127天，累计87个数据点，当前趋势上涨+15.3%",
    tags=["原材料", "成本", "追踪"],
    importance=0.8,
    source="report"
)

# 检索记忆
results = await memory.search(
    query="哪些话题在持续追踪？当前趋势如何？",
    org_id=org_uuid,
    limit=10
)

# 更新CEO画像
profile = await memory.get_ceo_profile(user_uuid)
updated_profile = await memory.update_from_interaction(
    user_id=user_uuid,
    interaction_type="report_read",
    data={"report_id": "...", "reading_time": 300, "clicked_sections": ["风险预警"]}
)
```

### 5.4 任务调度设计

```python
# tasks/scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler()

# 日报采集（每小时运行，采集当日增量）
scheduler.add_job(
    collect_articles,
    CronTrigger(hour="*", minute=0),  # 每小时整点
    args=["daily"],
    id="collect_daily"
)

# 日报生成（每天 7:30 运行）
scheduler.add_job(
    generate_daily_reports,
    CronTrigger(hour=7, minute=30),
    id="generate_daily"
)

# 晚报推送（每天 17:30 运行）
scheduler.add_job(
    push_evening_reports,
    CronTrigger(hour=17, minute=30),
    id="push_evening"
)

# 周报生成（每周一 8:00 运行）
scheduler.add_job(
    generate_weekly_reports,
    CronTrigger(day_of_week="mon", hour=8, minute=0),
    id="generate_weekly"
)

# 月报生成（每月1日 8:00 运行）
scheduler.add_job(
    generate_monthly_reports,
    CronTrigger(day=1, hour=8, minute=0),
    id="generate_monthly"
)

# 记忆整合（每天 23:00 运行，整理一天学到的新信息）
scheduler.add_job(
    consolidate_memories,
    CronTrigger(hour=23, minute=0),
    id="consolidate_memories"
)

# 爬虫健康检查（每5分钟运行）
scheduler.add_job(
    check_sources_health,
    CronTrigger(minute="*/5"),
    id="health_check"
)
```

---

## 六、Redis使用设计

### 6.1 Redis数据结构

```
# 1. 缓存层
cache:report:{report_id}           -> JSON (报告缓存，TTL=1h)
cache:topic:{topic_id}            -> JSON (主题配置缓存，TTL=5m)
cache:user:{user_id}:profile      -> JSON (用户画像缓存，TTL=30m)

# 2. 会话管理
session:{session_id}              -> Hash (用户会话数据，TTL=24h)
  - user_id
  - org_id
  - token_version

# 3. 消息队列（Streams）
queue:collection                   -> Stream (采集任务队列)
queue:report_generation            -> Stream (报告生成队列)
queue:push                         -> Stream (推送任务队列)

# 4. 分布式锁
lock:report_gen:{topic_id}         -> String (报告生成锁，防止重复生成)
lock:crawler:{source_id}           -> String (爬虫锁)

# 5. 限流
rate_limit:api:{user_id}           -> String (API调用计数，TTL=60s)
rate_limit:crawler:{source_id}     -> String (采集频率限制)

# 6. 计数
counter:articles:{topic_id}:{date} -> String (每日文章计数)
counter:api_calls:{user_id}:{date} -> String (每日API调用计数)

# 7. 临时数据
temp:article_dedup:{hash}          -> String (文章去重，TTL=7d)
temp:processing:{task_id}          -> Hash (任务处理状态)
```

### 6.2 Redis Streams 消费者组

```python
# 采集任务队列消费
import redis

r = redis.from_url(os.getenv("REDIS_URL"))

# 创建消费者组
r.xgroup_create("queue:collection", "workers", id="0", mkstream=True)

# 消费消息
while True:
    messages = r.xreadgroup(
        "workers",           # 组名
        "consumer-1",         # 消费者ID
        {"queue:collection": ">"},  # 读取新消息
        count=10,
        block=5000            # 阻塞5秒
    )
    
    for stream, msgs in messages:
        for msg_id, data in msgs:
            # 处理任务
            await process_article(data)
            # ACK
            r.xack("queue:collection", "workers", msg_id)
```

---

## 七、飞书集成设计

### 7.1 集成架构

```
┌─────────────────────────────────────────────────────────┐
│                    飞书开放平台                           │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │  消息推送    │  │  文档创建    │  │  日程管理    │     │
│  │  /send      │  │  /docx/create│  │  /calendar   │     │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘     │
└─────────┼────────────────┼────────────────┼──────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────┐
│                   Feishu Service                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  lark-oapi SDK                                  │    │
│  │  - 自动处理签名验证                              │    │
│  │  - 自动刷新 access_token                         │    │
│  │  - 事件订阅处理                                  │    │
│  └─────────────────────────────────────────────────┘    │
└───────────────────────────┬─────────────────────────────┘
                            │
                            ▼
                  ┌─────────────────────┐
                  │  数字员工后端        │
                  │  /api/v1/feishu/*   │
                  └─────────────────────┘
```

### 7.2 消息卡片设计

```python
# 飞书消息卡片示例
daily_report_card = {
    "msg_type": "interactive",
    "card": {
        "header": {
            "title": {"tag": "plain_text", "content": "📊 智闻日报 · 2025-05-22"},
            "template": "blue"
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**今日重点：**\n1. 🛢️ 原油上涨+2.3%，化工成本压力持续\n2. 📋 欧盟发布新能源补贴新规\n3. 💰 宁德时代宣布欧洲建厂计划"
                }
            },
            {"tag": "hr"},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看完整报告"},
                        "type": "primary",
                        "url": "{report_url}"
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "深度分析"},
                        "type": "default",
                        "url": "{analysis_url}"
                    }
                ]
            },
            {
                "tag": "note",
                "elements": [
                    {"tag": "plain_text", "content": "🔔 已开启自动推送 · 8:30 早报 / 18:00 晚报"}
                ]
            }
        ]
    }
}
```

### 7.3 报告文档模板

```markdown
# {{ report_title }}

**报告周期：** {{ start_date }} - {{ end_date }}
**生成时间：** {{ generated_at }}
**追踪主题：** {{ topic_name }}

---

## 📌 执行摘要

{{ executive_summary }}

---

## 🔥 今日重点事件

{% for item in key_events %}
### {{ loop.index }}. {{ item.title }}
- **来源：** {{ item.source }}
- **发布时间：** {{ item.published_at }}
- **重要性：** {{ item.importance }}/5
- **摘要：** {{ item.summary }}
{% endfor %}

---

## 📊 趋势分析

### {{ trend_1.title }}
{{ trend_1.description }}
- 走势：{{ trend_1.direction }}
- 数据：{{ trend_1.data }}

### {{ trend_2.title }}
{{ trend_2.description }}

---

## ⚠️ 风险预警

{% for risk in risks %}
### {{ risk.level }}级风险：{{ risk.title }}
{{ risk.description }}
- 概率：{{ risk.probability }}
- 影响：{{ risk.impact }}
{% endfor %}

---

## 💡 机会建议

{% for opportunity in opportunities %}
### {{ opportunity.title }}
{{ opportunity.description }}
- 建议行动：{{ opportunity.action }}
- 截止时间：{{ opportunity.deadline }}
{% endfor %}

---

## 📈 详细信息

{{ detailed_content }}

---

*本报告由 AI 自动生成 · 数字员工「智闻」*
```

---

## 八、前端架构

### 8.1 前端项目结构

```
frontend/
├── public/
│   └── index.html
├── src/
│   ├── api/                 # API调用
│   │   ├── auth.ts
│   │   ├── topics.ts
│   │   ├── reports.ts
│   │   └── memory.ts
│   ├── components/         # 公共组件
│   │   ├── Layout/
│   │   ├── Charts/
│   │   └── common/
│   ├── pages/               # 页面
│   │   ├── Dashboard/       # 仪表盘
│   │   ├── Topics/          # 主题配置
│   │   ├── Reports/         # 报告查看
│   │   ├── Memory/          # 记忆中心
│   │   ├── Analysis/        # 分析工具
│   │   └── Settings/         # 设置
│   ├── stores/              # 状态管理（Pinia）
│   ├── router/              # 路由
│   ├── styles/              # 全局样式
│   ├── utils/               # 工具函数
│   ├── App.vue
│   └── main.ts
├── .env.production
├── .env.development
└── vite.config.ts
```

### 8.2 页面清单

| 页面 | 路由 | 说明 |
|------|------|------|
| 登录/注册 | `/login`, `/register` | 认证 |
| 管理后台首页 | `/dashboard` | 概览统计 |
| 主题配置 | `/topics` | 主题增删改 |
| 报告列表 | `/reports` | 历史报告查看 |
| 报告详情 | `/reports/:id` | 报告内容 |
| 即时问答 | `/qa` | 实时对话 |
| 关联图谱 | `/graph` | 主题关联可视化 |
| 记忆中心 | `/memory` | 记忆检索/管理 |
| CEO画像 | `/profile` | 个人偏好设置 |
| 推送设置 | `/settings/push` | 推送渠道配置 |
| 新闻源管理 | `/sources` | 数据源配置 |

### 8.3 技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| 框架 | Vue3 + Composition API | 响应式前端 |
| 构建 | Vite | 快速构建工具 |
| UI库 | Ant Design Vue / Vant | 企业级组件 |
| 状态 | Pinia | Vue状态管理 |
| 路由 | Vue Router | 页面路由 |
| HTTP | Axios | API请求 |
| 图表 | ECharts | 数据可视化 |
| CSS | TailwindCSS | 工具类CSS |

---

## 九、部署架构

### 9.1 开发/测试环境

```yaml
# docker-compose.yml（开发环境）
version: '3.8'
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/digital_employee
      - REDIS_URL=redis://redis:6379/0
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - LARK_APP_ID=${LARK_APP_ID}
      - LARK_APP_SECRET=${LARK_APP_SECRET}
    depends_on:
      - db
      - redis
    volumes:
      - ./backend:/app

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend

  db:
    image: postgres:16
    environment:
      - POSTGRES_DB=digital_employee
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      - MINIO_ROOT_USER=minioadmin
      - MINIO_ROOT_PASSWORD=minioadmin

volumes:
  pgdata:
  redisdata:
```

### 9.2 生产环境架构

```
                    ┌─────────────────────────────────────────┐
                    │              用户访问                    │
                    │     (飞书 / Web浏览器 / 移动端)          │
                    └────────────────────┬──────────────────┘
                                         │
                                         ▼
                    ┌─────────────────────────────────────────┐
                    │           NGINX 反向代理                 │
                    │   SSL终止 · 负载均衡 · 静态资源缓存       │
                    └────────────────────┬──────────────────┘
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              │                          │                          │
              ▼                          ▼                          ▼
    ┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐
    │  API Server 1   │        │  API Server 2   │        │  API Server N   │
    │  (FastAPI)      │        │  (FastAPI)      │        │  (FastAPI)      │
    └────────┬────────┘        └────────┬────────┘        └────────┬────────┘
             │                          │                          │
             └──────────────────────────┼──────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
                    ▼                   ▼                   ▼
          ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
          │ PostgreSQL  │    │    Redis     │    │    MinIO     │
          │  +pgvector  │    │   Cluster    │    │   (S3兼容)   │
          │  (主从复制)  │    │  (哨兵模式)  │    │  (多节点)   │
          └──────────────┘    └──────────────┘    └──────────────┘
```

### 9.3 环境变量配置

```bash
# .env.production

# 应用
APP_NAME=DigitalEmployee
APP_ENV=production
DEBUG=false
SECRET_KEY=your-secret-key-here

# 数据库
DATABASE_URL=postgresql://user:pass@localhost:5432/digital_employee
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Redis
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=

# DeepSeek
DEEPSEEK_API_KEY=sk-xxxxx
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_EMBEDDING_MODEL=text-embedding-3-large

# 飞书
LARK_APP_ID=cli_xxxxx
LARK_APP_SECRET=xxxxx
LARK_VERIFICATION_TOKEN=xxxxx
LARK_ENCRYPT_KEY=xxxxx

# 对象存储
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=digital-employee

# 邮件（可选）
SMTP_HOST=smtp.mailgun.org
SMTP_PORT=587
SMTP_USER=postmaster@mg.yourdomain.com
SMTP_PASSWORD=xxxxx

# 日志
LOG_LEVEL=INFO
LOG_FORMAT=json
```

---

## 十、安全设计

### 10.1 认证与授权

```python
# JWT认证流程
1. 用户登录 → 验证密码 → 生成JWT Access Token + Refresh Token
2. Access Token（15分钟）用于API调用
3. Refresh Token（7天）用于续期Access Token
4. 登出时将Refresh Token加入黑名单

# Token结构
{
  "sub": "user_id",
  "org_id": "org_uuid",
  "role": "admin",
  "exp": 1234567890,
  "iat": 1234567800,
  "jti": "unique_token_id"
}

# 角色权限
- admin: 所有权限
- manager: 主题配置/报告查看/记忆管理
- user: 报告查看/记忆查看/即时问答
```

### 10.2 API安全

```python
# 安全措施
1. HTTPS强制
2. Rate Limiting（每用户每分钟60请求）
3. 输入验证（Pydantic schemas）
4. SQL注入防护（SQLAlchemy ORM）
5. XSS防护（前端Vue自动转义）
6. CORS配置（仅允许指定域名）
7. 请求ID追踪（用于日志审计）
```

### 10.3 数据安全

```python
# 敏感数据处理
1. 密码：Bcrypt哈希（cost=12）
2. API Key：加密存储
3. 用户数据：按组织隔离（org_id过滤）
4. 飞书Token：加密存储，定期刷新

# 审计日志
- 记录所有写操作（创建/更新/删除）
- 记录用户登录/登出
- 记录API调用（可选，敏感接口）
```

---

## 十一、监控系统

### 11.1 日志规范

```python
# JSON结构化日志
{
  "timestamp": "2025-05-22T10:30:00.000Z",
  "level": "INFO",
  "logger": "app.services.report",
  "message": "Report generated successfully",
  "context": {
    "report_id": "uuid",
    "topic_id": "uuid",
    "user_id": "uuid",
    "duration_ms": 1234,
    "request_id": "uuid"
  }
}
```

### 11.2 健康检查

```python
# /health 端点
{
  "status": "healthy",
  "version": "1.0.0",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "deepseek_api": "ok",
    "feishu_api": "ok"
  },
  "uptime": 3600
}
```

### 11.3 告警规则

| 告警项 | 条件 | 严重度 | 通知方式 |
|--------|------|--------|---------|
| API错误率 > 5% | 5分钟内 | 高 | 飞书/邮件 |
| 报告生成失败 | 连续3次 | 高 | 飞书/邮件 |
| 爬虫成功率 < 80% | 1小时内 | 中 | 邮件 |
| 数据库连接失败 | 立即 | 紧急 | 短信 |
| Redis连接失败 | 立即 | 紧急 | 短信 |
| 磁盘使用率 > 85% | 1小时内 | 中 | 邮件 |

---

## 十二、开发规范

### 12.1 Git工作流

```
feature/topic-config
feature/report-generation
fix/login-bug
refactor/ai-service
docs/api-design
```

### 12.2 代码规范

- **Python**: PEP 8 + Black格式化 + Ruff检查
- **TypeScript**: ESLint + Prettier
- **提交规范**: Conventional Commits

```bash
# 提交示例
feat(reports): add PDF export functionality
fix(auth): resolve token refresh race condition
docs(api): update endpoint documentation
refactor(ai): extract embedding logic to service
```

### 12.3 测试规范

```
tests/
├── unit/               # 单元测试
│   ├── services/
│   └── utils/
├── integration/        # 集成测试
│   └── api/
└── fixtures/          # 测试数据

# 覆盖率要求
- 核心服务：> 80%
- API路由：> 70%
- 工具函数：> 90%
```

---

## 附录

### A. 环境要求

| 组件 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 2核 | 4核+ |
| 内存 | 4GB | 8GB+ |
| 磁盘 | 50GB | 100GB+ SSD |
| PostgreSQL | 1GB RAM | 2GB+ RAM |

### B. 扩展路线

```
Phase 1（当前）：单体应用，PostgreSQL+Redis单节点
Phase 2：读写分离，Redis哨兵
Phase 3：分库分表，向量检索集群
Phase 4：多地域部署，边缘缓存
```

### C. 第三方服务成本估算（月）

| 服务 | 用量 | 成本 |
|------|------|------|
| DeepSeek API | ~100M tokens | ~$10 |
| 飞书专业版 | 1组织 | ¥30/人 |
| 云服务器（4核8G） | 1台 | ¥200 |
| OSS/S3存储 | 10GB | ¥2 |
| **合计** | | **~¥250 + $10** |
