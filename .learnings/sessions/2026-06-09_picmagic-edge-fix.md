# 2026-06-09 PicMagic 去背景边缘模糊修复 + 系统优化

## 讨论要点

### PicMagic 边缘模糊修复
- 原图有水印/文字时，rembg alpha 通道过渡区变宽 → 切边模糊
- 方向 A：换模型（BiRefNet 224MB）→ 下载成功但 OOM（3.6GB RAM）
- IS-Net (170MB) → 同样 OOM
- 方向 B：后处理优化 alpha 通道（纯 CPU，无新依赖）→ 选这个

### 系统优化
- **主动保存机制**：明确了 Memory/Skill 的保存策略和触发标准
- **跨Agent知识共享**：在项目目录创建 `.learnings/`（LEARNINGS.md + ERRORS.md + FEATURE_REQUESTS.md）
- **Session 自动归档**：复杂会话结束后压缩关键结论→`.learnings/sessions/`
- **cron 静默运行**：PicMagic 每日备份改为 `deliver=local`，不再发消息到飞书
- 确认了 Memory、`.learnings/`、Skill 三层防护体系

### 上下文丢失恢复
- 发现 session_search 只保留最近对话索引，旧的被 cron 会话挤掉了
- 无法恢复已丢失的对话历史
- 改进方案就是上述三层防护 + session 自动归档

## 决策

| 决策 | 理由 |
|------|------|
| 不换模型，走后处理 | 服务器内存有限(3.6GB)，大模型 OOM |
| Unsharp Mask on alpha，不碰 RGB | 过渡区缩小 46%，梯度提升 44%，远超 sigmoid(10%) |
| Memory 存关键决策 | 2200 字限制，只存最核心的 |
| `.learnings/` 存完整记录 | 磁盘无限，跨Agent共享 |
| Skill 存复杂工作流 | 完整知识库+踩坑记录 |
| cron deliver=local | 避免刷屏挤占 session 索引 |
| session 自动归档 | 防止重要讨论被索引淘汰丢失 |

## 技术细节

### alpha 边缘增强

```python
def _enhance_alpha_edge(alpha, amount=1.0):
    blurred = cv2.GaussianBlur(alpha, (0, 0), 2)
    alpha_f = alpha.astype(np.float32)
    sharpened = alpha_f + amount * (alpha_f - blurred)
    return np.clip(sharpened, 0, 255).astype(np.uint8)
```

**效果**：过渡区 2015→1091px（🔻46%），边缘梯度 639.7→920.5（🔺44%）

### Memory 5 问判断标准
1. 影响后续开发？
2. 忘了的话用户要重说？
3. 用户明确否定的方案？
4. 架构/技术选型理由？
5. 下次回来需要知道什么才能无缝继续？

任一肯定就存。

### Session 自动归档规则
- 你说"先到这里"/"下次继续" → 归档
- 复杂任务完成（5+工具调用）→ 归档
- 检测到 long idle → 自动归档

## 相关文件

- `/home/ubuntu/bg-eraser/backend/processor/engine.py` — remove_background() + _enhance_alpha_edge()
- `/home/ubuntu/bg-eraser/backend/render/engine.py` — _extract_product_mask() 边缘处理更新
- `/home/ubuntu/bg-eraser/backend/main.py` — /remove-bg 端点改用增强版
- `/home/ubuntu/lvb-digital-employee/.learnings/` — 项目级学习记录
- `/home/ubuntu/bg-eraser/.learnings/LEARNINGS.md` — PicMagic 专用学习记录
- `/home/ubuntu/.hermes/skills/software-development/bg-eraser/SKILL.md` — v2.1.0 更新
