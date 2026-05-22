# 数字员工 · 开发顺序规划
## Development Sequence Plan v1.0

> **项目代号：** 智闻（ZhiWen）
> **版本：** v1.0
> **日期：** 2025-05-22
> **状态：** 规划完成

---

## 一、优先级决策框架

### 1.1 开发顺序原则

```
┌─────────────────────────────────────────────────────────────────┐
│                     开发顺序决策矩阵                              │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   依赖关系      │   业务价值       │   技术复杂度                │
│   (必须先做)    │   (用户最需要)   │   (实现难度)                │
├───────────────┼─────────────────┼─────────────────────────────┤
│ ① 基础设施      │ ④ 报告生成       │ ⑥ AI分析                   │
│   DB/配置/Auth │   核心产品功能   │   SWOT/交叉验证              │
├───────────────┼─────────────────┼─────────────────────────────┤
│ ② 数据采集      │ ⑤ 推送系统       │ ⑦ 记忆系统                  │
│   爬虫/RSS    │   飞书集成       │   pgvector                   │
├───────────────┼─────────────────┼─────────────────────────────┤
│ ③ 主题配置      │ ① 基础设施       │ ② 数据采集                  │
│   用户配置入口  │   最底层依赖     │   技术成熟                   │
└───────────────┴─────────────────┴─────────────────────────────┘
```

### 1.2 四象限优先级

```
                    技术复杂度
              低              高
           ┌────────┬────────┐
业务价值    │  P2    │  P1    │
   高      │ 主题配置│ 报告生成│
           │ 推送系统│ AI分析 │
           ├────────┼────────┤
业务价值    │  P4    │  P3    │
   低      │ 管理后台│ 记忆系统│
           │ 前端UI │ 向量检索│
           └────────┴────────┘
```

| 优先级 | 功能 | 理由 |
|--------|------|------|
| **P1** | 报告生成 + AI分析 | 核心价值，用户付钱的原因 |
| **P2** | 主题配置 + 推送 | 用户配置入口+交付通道 |
| **P3** | 记忆系统 + 向量检索 | 差异化竞争力，越用越懂 |
| **P4** | 管理后台 + 前端UI | 效率工具，可后期补充 |

---

## 二、Phase 总览

```
Phase 1 ▸ 基础设施（2-3天）
  ├── 1.1 数据库设计 + 建表
  ├── 1.2 配置管理 + 环境变量
  ├── 1.3 认证系统（JWT）
  └── 1.4 项目骨架（FastAPI路由）

Phase 2 ▸ 数据采集层（3-4天）
  ├── 2.1 新闻源管理（CRUD）
  ├── 2.2 RSS采集器
  ├── 2.3 HTTP爬虫（httpx）
  ├── 2.4 Playwright渲染爬虫
  ├── 2.5 文章解析（标题/正文/时间）
  └── 2.6 任务队列（Redis Streams）

Phase 3 ▸ 主题配置 + 报告生成（4-5天）
  ├── 3.1 主题CRUD API
  ├── 3.2 主题-新闻源关联
  ├── 3.3 文章聚合+去重
  ├── 3.4 AI摘要生成
  ├── 3.5 报告生成（多模板）
  └── 3.6 定时任务调度（APScheduler）

Phase 4 ▸ 飞书集成 + 推送（2-3天）
  ├── 4.1 飞书授权 + OAuth
  ├── 4.2 消息卡片推送
  ├── 4.3 飞书文档生成
  ├── 4.4 推送配置管理
  └── 4.5 推送记录管理

Phase 5 ▸ AI分析引擎（3-4天）
  ├── 5.1 交叉验证分析
  ├── 5.2 SWOT分析
  ├── 5.3 风险评估
  └── 5.4 机会识别

Phase 6 ▸ 记忆系统（3-4天）
  ├── 6.1 向量嵌入服务
  ├── 6.2 记忆CRUD API
  ├── 6.3 记忆检索（pgvector）
  ├── 6.4 CEO画像
  └── 6.5 记忆整合任务

Phase 7 ▸ 前端开发（4-5天）
  ├── 7.1 项目骨架 + 路由
  ├── 7.2 主题配置页面
  ├── 7.3 报告列表+详情页
  ├── 7.4 即时问答页
  ├── 7.5 关联图谱页
  └── 7.6 记忆中心页

Phase 8 ▸ 高级功能（2-3天）
  ├── 8.1 开放API
  ├── 8.2 Webhook
  └── 8.3 监控告警
```

---

## 三、Phase 1 · 基础设施

### 目标：搭建开发环境，数据库+认证+骨架

```
⏱️ 预计工期：2-3天
📦 产出物：可运行的空壳项目，数据库就绪
🎯 里程碑：能注册登录，API可访问
```

#### Task 1.1：初始化项目结构

```
backend/
├── app/
│   ├── api/v1/
│   │   ├── __init__.py
│   │   ├── auth.py      # 认证路由
│   │   ├── users.py     # 用户路由
│   │   ├── topics.py     # 主题路由
│   │   ├── sources.py    # 新闻源路由
│   │   ├── reports.py    # 报告路由
│   │   ├── memory.py     # 记忆路由
│   │   └── analysis.py   # 分析路由
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py     # 配置管理
│   │   ├── security.py   # JWT/加密
│   │   └── database.py   # 数据库连接
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── topic.py
│   │   ├── source.py
│   │   ├── article.py
│   │   ├── report.py
│   │   └── memory.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── topic.py
│   │   ├── source.py
│   │   ├── report.py
│   │   └── memory.py
│   └── main.py          # FastAPI入口
├── tests/
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── requirements.txt
```

#### Task 1.2：配置管理（config.py）

```python
# backend/app/core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "数字员工"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # 数据库
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/digital_employee"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # DeepSeek
    DEEPSEEK_API_KEY: str
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_EMBEDDING_MODEL: str = "text-embedding-3-large"
    
    # 飞书
    LARK_APP_ID: str
    LARK_APP_SECRET: str
    
    # MinIO
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "digital-employee"

    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings():
    return Settings()
```

#### Task 1.3：数据库连接（database.py）

```python
# backend/app/core/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=10
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

#### Task 1.4：用户模型（user.py）

```python
# backend/app/models/user.py
from sqlalchemy import Column, String, Boolean, DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20))
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user")  # admin/manager/user
    org_id = Column(UUID(as_uuid=True), index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

#### Task 1.5：建表SQL（init.sql）

```sql
-- 启用扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- 建表语句（所有11张表，见技术架构文档3.2节）

-- 初始化主题分类数据
INSERT INTO topic_categories (name, code, description) VALUES
  ('政策宏观', 'A', '政府政策、监管动态、宏观数据'),
  ('资本市场', 'B', '投融资、并购、IPO、二级市场'),
  ('行业动态', 'C', '竞品、行业报告、技术趋势'),
  ('经济数据', 'D', 'GDP、CPI、PPI、行业数据、财报'),
  ('国际形势', 'E', '地缘政治、国际关系、汇率');

-- 初始化默认管理员
INSERT INTO users (username, email, password_hash, role) VALUES
  ('admin', 'admin@example.com', '$2b$12$...', 'admin');
```

#### Task 1.6：JWT认证（security.py）

```python
# backend/app/core/security.py
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
```

#### Task 1.7：认证API（auth.py）

```python
# backend/app/api/v1/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_password, get_password_hash, create_access_token, decode_token
from app.models.user import User
from app.schemas.user import UserLogin, UserRegister, Token

router = APIRouter(prefix="/auth", tags=["认证"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

@router.post("/register", response_model=Token)
def register(data: UserRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="邮箱已注册")
    user = User(
        username=data.username,
        email=data.email,
        password_hash=get_password_hash(data.password)
    )
    db.add(user)
    db.commit()
    access_token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login", response_model=Token)
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    access_token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token无效")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user
```

---

## 四、Phase 2 · 数据采集层

### 目标：新闻源管理 + 多方式采集 + 任务队列

```
⏱️ 预计工期：3-4天
📦 产出物：文章入库，可触发采集
🎯 里程碑：能手动添加新闻源，抓到文章
```

### Task 2.1：新闻源模型 + CRUD

```python
# backend/app/models/source.py
class NewsSource(Base):
    __tablename__ = "news_sources"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    source_type = Column(String(20), nullable=False)  # rss/api/crawl
    url = Column(Text, nullable=False)
    update_freq = Column(String(20), default="1h")
    is_active = Column(Boolean, default=True)
    last_fetch_at = Column(DateTime)
    last_fetch_status = Column(String(20))
    config = Column(JSONB)  # headers/auth等
    created_at = Column(DateTime, default=datetime.utcnow)
```

### Task 2.2：RSS采集器

```python
# backend/app/services/rss.py
import feedparser
from datetime import datetime
from app.models.source import NewsSource

async def fetch_rss(source: NewsSource) -> list[dict]:
    """采集RSS订阅源"""
    feed = feedparser.parse(source.url)
    articles = []
    for entry in feed.entries:
        articles.append({
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "published_at": datetime(*entry.published_parsed[:6]) if entry.get("published_parsed") else None,
            "content": entry.get("summary", ""),
            "source_name": source.name,
            "source_id": str(source.id)
        })
    return articles
```

### Task 2.3：HTTP爬虫（httpx异步）

```python
# backend/app/services/crawler.py
import httpx
from app.models.source import NewsSource

async def fetch_web(source: NewsSource) -> list[dict]:
    """异步HTTP采集"""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(source.url)
        response.raise_for_status()
        # 后续解析HTML（用BeautifulSoup）
        return parse_html(response.text, source)
```

### Task 2.4：Playwright渲染爬虫

```python
# backend/app/services/crawler.py
from playwright.async_api import async_playwright

async def fetch_dynamic(source: NewsSource) -> list[dict]:
    """JS渲染页面采集"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(source.url, wait_until="networkidle")
        # 提取数据
        content = await page.content()
        await browser.close()
        return parse_html(content, source)
```

### Task 2.5：文章解析

```python
# backend/app/services/parser.py
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

def parse_html(html: str, source: NewsSource) -> dict:
    """解析HTML提取文章信息"""
    soup = BeautifulSoup(html, "html.parser")
    
    # 提取标题
    title = soup.find("h1") or soup.find("title")
    
    # 提取正文（通用方法，可能需要针对不同站点调整）
    article_body = soup.find("article") or soup.find("div", class_="content")
    
    # 提取发布时间
    time_elem = soup.find("time") or soup.find("span", class_="date")
    published_at = date_parser.parse(time_elem["datetime"]) if time_elem else None
    
    return {
        "title": title.text.strip() if title else "",
        "content": article_body.text.strip() if article_body else "",
        "published_at": published_at,
        "url": source.url
    }
```

### Task 2.6：Redis Streams任务队列

```python
# backend/app/services/queue.py
import redis
import json
from app.core.config import get_settings

settings = get_settings()
r = redis.from_url(settings.REDIS_URL, decode_responses=True)

QUEUE_NAME = "queue:collection"

async def enqueue_collect_task(source_id: str, url: str, priority: int = 2):
    """添加采集任务到队列"""
    task = json.dumps({
        "source_id": source_id,
        "url": url,
        "priority": priority,
        "enqueued_at": datetime.utcnow().isoformat()
    })
    r.xadd(QUEUE_NAME, {"task": task})

async def consume_collect_tasks():
    """消费采集任务（Worker调用）"""
    group_name = "collectors"
    consumer_name = f"worker-{os.getpid()}"
    
    # 确保消费者组存在
    try:
        r.xgroup_create(QUEUE_NAME, group_name, id="0", mkstream=True)
    except redis.ResponseError:
        pass  # 组已存在
    
    while True:
        messages = r.xreadgroup(
            group_name, consumer_name,
            {QUEUE_NAME: ">"},
            count=10, block=5000
        )
        for stream, msgs in messages:
            for msg_id, data in msgs:
                task = json.loads(data["task"])
                yield msg_id, task
                r.xack(QUEUE_NAME, group_name, msg_id)
```

---

## 五、Phase 3 · 主题配置 + 报告生成

### 目标：用户配置主题 → AI自动生成报告

```
⏱️ 预计工期：4-5天
📦 产出物：完整报告生成流程
🎯 里程碑：选主题 → 生成日报 → 推送飞书
```

### Task 3.1：主题CRUD API

```python
# backend/app/api/v1/topics.py
class TopicCreate(BaseModel):
    name: str
    category: str  # A/B/C/D/E
    keywords: list[str]
    exclude_keywords: list[str] = []
    push_cycle: str = "daily"  # daily/weekly/monthly
    push_time: str = "08:30"

@router.post("/", response_model=Topic)
def create_topic(data: TopicCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    topic = Topic(
        org_id=user.org_id,
        user_id=user.id,
        **data.model_dump()
    )
    db.add(topic)
    db.commit()
    return topic

@router.get("/")
def list_topics(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Topic).filter(Topic.org_id == user.org_id, Topic.is_active == True).all()
```

### Task 3.2：主题-新闻源关联

```python
# backend/app/models/topic.py
class TopicSource(Base):
    __tablename__ = "topic_sources"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="CASCADE"))
    source_id = Column(UUID(as_uuid=True), ForeignKey("news_sources.id", ondelete="CASCADE"))
    weight = Column(Float, default=1.0)
```

### Task 3.3：文章聚合 + 去重

```python
# backend/app/services/report.py
async def collect_articles_for_topic(topic_id: str, days: int = 1) -> list[Article]:
    """收集主题相关文章（按关键词匹配）"""
    topic = db.query(Topic).get(topic_id)
    keywords = topic.keywords
    
    # 查询近期文章
    cutoff = datetime.utcnow() - timedelta(days=days)
    articles = db.query(Article).filter(
        Article.fetched_at >= cutoff,
        Article.is_processed == False
    ).all()
    
    # 关键词匹配 + 去重
    matched = []
    seen_urls = set()
    for article in articles:
        if article.url in seen_urls:
            continue
        if matches_keywords(article.title + " " + (article.content or ""), keywords):
            matched.append(article)
            seen_urls.add(article.url)
    
    return matched

def matches_keywords(text: str, keywords: list[str]) -> bool:
    """检查文本是否匹配关键词"""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)
```

### Task 3.4：AI摘要生成

```python
# backend/app/services/ai.py
class AIService:
    async def generate_summary(self, texts: list[str], max_length: int = 500) -> str:
        """将多篇文章合并生成摘要"""
        prompt = f"""请阅读以下{len(texts)}篇文章，生成一份简洁的摘要（不超过{max_length}字）：

{"="*50}".join([f"文章{i+1}：{t[:500]}" for i, t in enumerate(texts)])}

摘要："""
        
        response = await self._call_deepseek(prompt)
        return response["choices"][0]["message"]["content"]
    
    async def _call_deepseek(self, prompt: str, system: str = "你是一个专业的行业分析助手。") -> dict:
        """调用DeepSeek API"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}"},
                json={
                    "model": settings.DEEPSEEK_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt}
                    ]
                }
            )
            return response.json()
```

### Task 3.5：报告生成服务

```python
# backend/app/services/report.py
class ReportService:
    async def generate_daily_report(self, topic_id: str) -> Report:
        """生成日报"""
        # 1. 收集文章
        articles = await self.collect_articles_for_topic(topic_id, days=1)
        
        # 2. AI生成摘要
        contents = [a.content or "" for a in articles]
        summary = await self.ai.generate_summary(contents)
        
        # 3. SWOT分析
        swot = await self.ai.analyze_swot(topic.name, articles)
        
        # 4. 风险评估
        risks = await self.ai.assess_risk(topic.name, articles)
        
        # 5. 创建报告
        report = Report(
            topic_id=topic_id,
            report_type="daily",
            title=f"{topic.name} 日报 · {date.today()}",
            summary=summary,
            swot=swot,
            risk_items=risks,
            status="generated"
        )
        db.add(report)
        db.commit()
        return report
```

### Task 3.6：定时任务调度

```python
# backend/app/tasks/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler()

# 日报生成（每天 7:30）
scheduler.add_job(
    generate_all_daily_reports,
    CronTrigger(hour=7, minute=30),
    id="generate_daily_reports"
)

# 晚报推送（每天 17:30）
scheduler.add_job(
    push_all_evening_reports,
    CronTrigger(hour=17, minute=30),
    id="push_evening_reports"
)

# 文章采集（每小时）
scheduler.add_job(
    collect_all_sources,
    CronTrigger(minute=0),
    id="collect_articles"
)

scheduler.start()
```

---

## 六、Phase 4 · 飞书集成 + 推送

### 目标：推送报告到飞书

```
⏱️ 预计工期：2-3天
📦 产出物：飞书消息卡片推送
🎯 里程碑：报告生成后自动推送到飞书
```

### Task 4.1：飞书SDK集成

```python
# backend/app/services/feishu.py
from lark_oapi import lark
from app.core.config import get_settings

settings = get_settings()

class FeishuService:
    def __init__(self):
        self.client = lark.Client.builder()\
            .app_id(settings.LARK_APP_ID)\
            .app_secret(settings.LARK_APP_SECRET)\
            .build()
    
    def send_message(self, open_id: str, card: dict) -> dict:
        """发送消息卡片"""
        return self.client.im.v1.message.create(
            lark.PATCH_TYPE_POST,
            "open_id",
            open_id,
            body=lark.CreateMessageRequestBody(
                msg_type="interactive",
                content=json.dumps(card)
            )
        )
    
    def create_document(self, title: str, content: str) -> str:
        """创建飞书文档，返回doc_token"""
        doc = self.client.docx.v1.document.create(
            CreateDocumentRequestBody(title=title, document_style=None)
        )
        # 写入内容...
        return doc.data.document.document_id
```

### Task 4.2：消息卡片模板

```python
# backend/app/services/feishu.py
DAILY_REPORT_CARD = {
    "msg_type": "interactive",
    "card": {
        "header": {
            "title": {"tag": "plain_text", "content": "📊 智闻日报 · {date}"},
            "template": "blue"
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": "**今日重点**\n{items}"}},
            {"tag": "hr"},
            {
                "tag": "action",
                "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "查看完整报告"},
                     "type": "primary", "url": "{report_url}"},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "深度分析"},
                     "type": "default", "url": "{analysis_url}"}
                ]
            }
        ]
    }
}
```

---

## 七、Phase 5 · AI分析引擎

### 目标：深度分析能力

```
⏱️ 预计工期：3-4天
📦 产出物：SWOT分析/交叉验证/风险评估/机会识别
🎯 里程碑：报告包含完整的AI分析结果
```

### Task 5.1：SWOT分析

```python
async def analyze_swot(self, topic: str, articles: list[Article]) -> dict:
    """SWOT四象限分析"""
    prompt = f"""分析以下关于「{topic}」的信息，进行SWOT分析：

文章列表：
{chr(10).join([f"- {a.title}：{a.content[:300]}" for a in articles[:10]])}

请以JSON格式输出：
{{
  "strengths": ["优势1", "优势2"],
  "weaknesses": ["劣势1", "劣势2"],
  "opportunities": ["机会1", "机会2"],
  "threats": ["威胁1", "威胁2"]
}}
只输出JSON，不要其他内容。"""
    
    response = await self._call_deepseek(prompt)
    return json.loads(response["choices"][0]["message"]["content"])
```

### Task 5.2：交叉验证分析

```python
async def cross_validate(self, article_ids: list[str], claim: str) -> dict:
    """多源交叉验证"""
    articles = [db.query(Article).get(id) for id in article_ids]
    
    prompt = f"""请验证以下观点：「{claim}」

文章证据：
{chr(10).join([f"[{i+1}] {a.title}：{a.content[:500]}" for i, a in enumerate(articles)])}

分析要求：
1. 找出支持该观点的证据（标注来源可靠性）
2. 找出反驳该观点的证据
3. 给出置信度评估（高/中/低）
4. 区分「确认事实」和「AI推断」

以JSON格式输出。"""
    
    response = await self._call_deepseek(prompt)
    return json.loads(response["choices"][0]["message"]["content"])
```

### Task 5.3：风险评估

```python
async def assess_risk(self, topic: str, articles: list[Article]) -> dict:
    """风险评估"""
    prompt = f"""识别关于「{topic}」的风险：

文章：
{chr(10).join([f"- {a.title}：{a.content[:300]}" for a in articles[:10]])}

分析要求：
1. 识别3-5个关键风险
2. 评估每个风险的：概率（高/中/低）、影响程度、紧迫性
3. 给出风险等级（高/中/低）

以JSON格式输出：
{{
  "risk_level": "high",
  "risks": [
    {{"title": "风险标题", "probability": "high", "impact": "high", "urgency": "high"}}
  ]
}}"""
    
    response = await self._call_deepseek(prompt)
    return json.loads(response["choices"][0]["message"]["content"])
```

---

## 八、Phase 6 · 记忆系统

### 目标：向量检索 + CEO画像 + 话题追踪

```
⏱️ 预计工期：3-4天
📦 产出物：记忆检索API + CEO画像
🎯 里程碑：报告内容自动沉淀为记忆，支持检索
```

### Task 6.1：向量嵌入服务

```python
# backend/app/services/vector.py
EMBEDDING_DIM = 1536  # DeepSeek embedding dimension

class VectorService:
    async def embed_text(self, text: str) -> list[float]:
        """获取文本的向量表示"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.deepseek.com/v1/embeddings",
                headers={"Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}"},
                json={
                    "model": settings.DEEPSEEK_EMBEDDING_MODEL,
                    "input": text[:8000]  # 模型有token限制
                }
            )
            result = response.json()
            return result["data"][0]["embedding"]
```

### Task 6.2：记忆存储 + pgvector

```python
# backend/app/services/memory.py
class MemoryService:
    async def add_memory(self, org_id: str, content: str, memory_type: str, **kwargs) -> Memory:
        """添加记忆（自动生成向量）"""
        embedding = await self.vector_service.embed_text(content)
        
        memory = Memory(
            org_id=org_id,
            content=content,
            memory_type=memory_type,
            embedding=embedding,
            **kwargs
        )
        db.add(memory)
        db.commit()
        return memory
    
    async def search_memory(self, query: str, org_id: str, memory_type: str = None, limit: int = 5) -> list[Memory]:
        """向量相似度搜索"""
        query_embedding = await self.vector_service.embed_text(query)
        
        sql = text("""
            SELECT id, content, memory_type, importance,
                   1 - (embedding <=> :query_emb) AS similarity
            FROM memories
            WHERE org_id = :org_id
              AND is_active = TRUE
              AND (:memory_type IS NULL OR memory_type = :memory_type)
            ORDER BY embedding <=> :query_emb
            LIMIT :limit
        """)
        
        result = db.execute(sql, {
            "query_emb": query_embedding,
            "org_id": org_id,
            "memory_type": memory_type,
            "limit": limit
        })
        return result.fetchall()
```

### Task 6.3：CEO画像

```python
async def get_ceo_profile(self, user_id: str) -> dict:
    """获取CEO画像"""
    memories = db.query(Memory).filter(
        Memory.user_id == user_id,
        Memory.memory_type.in_(["preference", "behavior"]),
        Memory.is_active == True
    ).order_by(Memory.importance.desc()).limit(20).all()
    
    # AI总结画像
    summary = await self.ai.summarize_profile(memories)
    
    return {
        "completeness": len(memories) / 50,  # 假设50项完整
        "preferences": extract_preferences(memories),
        "tracking_topics": get_tracking_topics(user_id),
        "ai_insights": summary
    }
```

---

## 九、Phase 7 · 前端开发

### 目标：管理后台 + H5页面

```
⏱️ 预计工期：4-5天
📦 产出物：可用的Web管理界面
🎯 里程碑：完整的产品体验
```

### 页面开发顺序

| 顺序 | 页面 | 理由 |
|------|------|------|
| 1 | 登录/注册 | 入口 |
| 2 | 主题配置 | 核心配置 |
| 3 | 报告列表/详情 | 核心价值交付 |
| 4 | 即时问答 | 差异化功能 |
| 5 | 记忆中心 | 增值功能 |
| 6 | 管理后台 | 效率工具 |

### 页面技术选型

```
管理后台（PC）：React + Ant Design + TailwindCSS
H5（手机端）：Vue3 + Vant
状态管理：Pinia
路由：Vue Router
HTTP：Axios
图表：ECharts
```

---

## 十、Phase 8 · 高级功能

### 目标：开放API + Webhook + 监控

```
⏱️ 预计工期：2-3天
📦 产出物：开放平台能力
🎯 里程碑：可对外提供API服务
```

---

## 十一、依赖关系图

```
Phase 1（基础设施）
    │
    │ ✅ 必先完成
    ▼
Phase 2（数据采集）
    │
    │ 依赖 Phase 1 的数据库和模型
    ▼
Phase 3（主题+报告）◄────────┐
    │                        │
    │ 依赖 Phase 2 的文章    │
    │ 依赖 Phase 1 的认证   │
    ▼                        │
Phase 4（飞书+推送）─────────┘
    │
    │ 依赖 Phase 3 的报告
    ▼
Phase 5（AI分析）
    │
    │ 依赖 Phase 3 的报告
    ▼
Phase 6（记忆系统）
    │
    │ 独立，可提前做（Phase 3之后）
    ▼
Phase 7（前端）◄──┐
    │            │
    │ 依赖所有后端API
    ▼            │
Phase 8（开放API）┘
```

---

## 十二、里程碑时间线

```
Week 1 ░░░░░░░░░░░░░░░░░░░░░
  Phase 1 ████░░░░ 基础设施
  Phase 2 ████████░░░░░░░░░ 数据采集（并行）

Week 2 ░░░░░░░░░░░░░░░░░░░░░
  Phase 2 ████░░░░░░░ 收尾
  Phase 3 ████████████████ 主题+报告生成

Week 3 ░░░░░░░░░░░░░░░░░░░░░
  Phase 3 ████░░░░ 收尾
  Phase 4 ██████░░░░░░ 飞书+推送
  Phase 5 ████████████░░░░░ AI分析

Week 4 ░░░░░░░░░░░░░░░░░░░░░
  Phase 5 ██░░░░░░ 收尾
  Phase 6 ████████████░░░░░ 记忆系统
  Phase 7 ████████████░░░░░ 前端开发

Week 5 ░░░░░░░░░░░░░░░░░░░░░
  Phase 7 ████████░░░░░░░░░░ 前端（续）
  Phase 8 ████░░░░░░░░░░░░░░ 开放API

Week 6 ░░░░░░░░░░░░░░░░░░░░░
  集成测试 + Bug修复
  部署上线
```

---

## 十三、关键风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| 爬虫被封 | Phase 2延迟 | 使用代理池+低频采集+Playwright模拟真人 |
| DeepSeek API限流 | 报告生成慢 | 添加请求队列+重试机制 |
| 飞书API变更 | 推送失败 | 版本锁定+官方SDK+回调监控 |
| pgvector性能 | 检索慢 | 定期VACUUM+索引优化+IVFFlat |
| 前端工期超期 | 上线延误 | 优先完成核心页面，高级UI后期迭代 |

---

## 十四、下一步行动

```
□ 1. 确认开发顺序是否合理
□ 2. 确定Phase 1的详细任务分解（每个Task 2-5分钟）
□ 3. 分配开发资源（谁做哪个Phase）
□ 4. 制定Phase 1的代码规范和PR流程
□ 5. 开始Phase 1开发
```

**你想先做哪个Phase？我可以从Phase 1开始，输出每个Task的详细代码。**
