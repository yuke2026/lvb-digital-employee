-- =====================================================
-- LVB Digital Employee - Database Initialization Script
-- PostgreSQL with pgvector extension
-- =====================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================
-- 1. organizations
-- =====================================================
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    industry VARCHAR(50),
    scale VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

-- =====================================================
-- 2. users
-- =====================================================
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(20),
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'user',
    org_id UUID REFERENCES organizations(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_users_org ON users(org_id);
CREATE INDEX idx_users_email ON users(email);

-- =====================================================
-- 3. topics
-- =====================================================
CREATE TABLE topics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    keywords TEXT[] NOT NULL,
    exclude_keywords TEXT[],
    push_cycle VARCHAR(20) DEFAULT 'daily',
    push_time TIME DEFAULT '08:30:00',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_topics_org ON topics(org_id);
CREATE INDEX idx_topics_active ON topics(is_active) WHERE is_active = TRUE;

-- =====================================================
-- 4. news_sources
-- =====================================================
CREATE TABLE news_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    source_type VARCHAR(20) NOT NULL,
    url TEXT NOT NULL,
    update_freq VARCHAR(20) DEFAULT '1h',
    is_active BOOLEAN DEFAULT TRUE,
    last_fetch_at TIMESTAMP,
    last_fetch_status VARCHAR(20),
    config JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_news_sources_org ON news_sources(org_id);
CREATE INDEX idx_news_sources_active ON news_sources(is_active);

-- =====================================================
-- 5. topic_sources (M2M relationship)
-- =====================================================
CREATE TABLE topic_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID REFERENCES topics(id) ON DELETE CASCADE,
    source_id UUID REFERENCES news_sources(id) ON DELETE CASCADE,
    weight FLOAT DEFAULT 1.0,
    UNIQUE(topic_id, source_id)
);

-- =====================================================
-- 6. raw_articles
-- =====================================================
CREATE TABLE raw_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES news_sources(id),
    url TEXT NOT NULL,
    title VARCHAR(500) NOT NULL,
    content TEXT,
    summary TEXT,
    published_at TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT NOW(),
    vector_embedding VECTOR(1536),
    language VARCHAR(10) DEFAULT 'zh',
    is_processed BOOLEAN DEFAULT FALSE,
    duplicate_of UUID REFERENCES raw_articles(id),
    metadata JSONB
);

CREATE INDEX idx_raw_articles_source ON raw_articles(source_id);
CREATE INDEX idx_raw_articles_published ON raw_articles(published_at DESC);
CREATE INDEX idx_raw_articles_processed ON raw_articles(is_processed) WHERE is_processed = FALSE;
CREATE INDEX idx_raw_articles_emb ON raw_articles USING ivfflat (vector_embedding vector_cosine_ops);

-- =====================================================
-- 7. reports
-- =====================================================
CREATE TABLE reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID REFERENCES topics(id) ON DELETE CASCADE,
    report_type VARCHAR(20) NOT NULL,
    title VARCHAR(300) NOT NULL,
    summary TEXT,
    content JSONB,
    swot JSONB,
    risk_level VARCHAR(10),
    risk_items JSONB,
    opportunities JSONB,
    push_time TIMESTAMP,
    status VARCHAR(20) DEFAULT 'draft',
    feishu_doc_token VARCHAR(100),
    feishu_msg_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_reports_topic ON reports(topic_id);
CREATE INDEX idx_reports_type ON reports(report_type);
CREATE INDEX idx_reports_created ON reports(created_at DESC);

-- =====================================================
-- 8. report_items
-- =====================================================
CREATE TABLE report_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID REFERENCES reports(id) ON DELETE CASCADE,
    article_id UUID REFERENCES raw_articles(id),
    title VARCHAR(300),
    summary TEXT,
    importance FLOAT DEFAULT 0.5,
    source_confidence FLOAT DEFAULT 0.5,
    is_key_event BOOLEAN DEFAULT FALSE,
    tag VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_report_items_report ON report_items(report_id);

-- =====================================================
-- 9. memories
-- =====================================================
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    memory_type VARCHAR(30) NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1536),
    importance FLOAT DEFAULT 0.5,
    source VARCHAR(50),
    source_id UUID,
    tags TEXT[],
    is_active BOOLEAN DEFAULT TRUE,
    last_accessed_at TIMESTAMP,
    access_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_memories_org ON memories(org_id);
CREATE INDEX idx_memories_type ON memories(memory_type);
CREATE INDEX idx_memories_emb ON memories USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_memories_importance ON memories(importance DESC) WHERE is_active = TRUE;

-- =====================================================
-- 10. push_records
-- =====================================================
CREATE TABLE push_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id UUID REFERENCES reports(id),
    channel VARCHAR(20) NOT NULL,
    recipient VARCHAR(100),
    status VARCHAR(20) DEFAULT 'pending',
    sent_at TIMESTAMP,
    error_msg TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_push_records_report ON push_records(report_id);
CREATE INDEX idx_push_records_status ON push_records(status);

-- =====================================================
-- 11. user_prefs
-- =====================================================
CREATE TABLE user_prefs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    pref_key VARCHAR(50) NOT NULL,
    pref_value TEXT,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, pref_key)
);

-- =====================================================
-- Sample data (uncomment to use)
-- =====================================================

-- INSERT INTO organizations (name, industry, scale) VALUES 
-- ('示例公司', '科技', '中型');

-- INSERT INTO users (username, email, phone, password_hash, role, org_id) VALUES
-- ('admin', 'admin@example.com', '13800138000', '$2b$12$...', 'admin', NULL);
