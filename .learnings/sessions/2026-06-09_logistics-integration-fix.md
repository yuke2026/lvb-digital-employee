# 2026-06-09 驿递通集成修复 — 前端缺少 operations 分类

## 问题

git commit `c9e23c2` "feat: 集成驿递通·物流客服数字员工到百应智星" 只做了后端集成，前端缺少物流客服的入口。

## 根因

后端 seed data 中物流客服的 `category: "operations"`，但前端的 3 个员工分组过滤器都不包含这个分类：

| 分组 | 过滤器 | 缺？ |
|------|--------|:---:|
| 核心大脑 | `core \| intelligence` | ❌ |
| 产研团队 | `management \| engineering \| design` | ❌ |
| 运营&销售 | `marketing \| sales` | ❌ 缺 `operations` |

## 修复

在 2 个地方补了 `operations` 到过滤器：
1. 商店页员工卡片网格（line 1581）
2. 聊天页左侧导航（line 1689）

同时更新了标签映射：`{'marketing':'营销','sales':'销售','operations':'物流运营'}`

## 经验

**提交检查清单**：集成新数字员工到百应智星时，必须确认：
- [ ] 后端 seed data → `backend/app/services/db.py`
- [ ] 后端 API 路由 → `backend/app/api/v1/`
- [ ] 后端 main.py 注册路由
- [ ] 前端商店页过滤器 → `frontend/index.html` (商店 grid)
- [ ] 前端聊天页过滤器 → `frontend/index.html` (侧栏 nav)
- [ ] 前端标签映射 → `x-text` 中的 `{'marketing':'营销',...}`

## 相关文件
- `/home/ubuntu/lvb-digital-employee/frontend/index.html` — 商店页 line 1581, 侧栏 line 1689
- `/home/ubuntu/lvb-digital-employee/backend/app/services/db.py` — seed data line 184
