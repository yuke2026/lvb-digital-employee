# Session 存档

每次复杂会话结束后的关键结论归档，防止 session 索引淘汰导致丢失。

## 命名规则

`YYYY-MM-DD_topic-slug.md`

## 内容

每篇存档包含：讨论要点、决策及理由、技术细节、相关文件路径。

## 如何搜索

```bash
grep -l "关键词" .learnings/sessions/*.md
```

## 关联

- `.learnings/LEARNINGS.md` — 跨Agent共享的修正记录
- `.learnings/ERRORS.md` — 技术踩坑记录
- `.learnings/FEATURE_REQUESTS.md` — 功能需求
