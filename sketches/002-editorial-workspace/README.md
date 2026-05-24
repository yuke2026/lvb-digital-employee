## Variant: Editorial Workspace（专业工作台）

### Design stance
**浅色 + 留白 + 内容优先** — 借鉴 Notion/飞书的轻盈感，弱化"工具感"，强化"专业顾问"的权威和信任感。

### Key choices
- **Layout**: 左右分栏 — 左侧功能区（更轻的导航）→ 右侧对话区（65%），右边叠一个可滚动任务配置面板（35%）。聊天仍然是主场景。
- **Color**: 浅灰背景（#f7f8fc）+ 纯白卡片 + 蓝色主色调（#2563eb）。清爽、干净、企业级。
- **Typography**: Inter 字体（Google Fonts），比系统字体更有设计感。14-15px 基准字号，略大更易读。
- **Expert card**: 横向排列，圆形头像+名称+简介+在线状态，Notion 式简洁。
- **Task panel**: 浅色 Card 列表+Toss开关，报告卡片有 hover 上浮效果。操作感和精致感并存。
- **Input**: 胶囊形输入框+圆形发送按钮，Notion/Twitter式，极简。
- **Interactive**: Pill 快捷标签（点击切换 active）、Toggle 开关、报告卡片 hover、消息发送、进度条动画、输入框回车发送。

### Trade-offs
- **Strong at**: 视觉清新专业、对话体验沉浸、留白多让内容呼吸、适合长时间使用
- **Weak at**: 信息密度低、自动化面板内容多时需要滚动、不如深色版一眼掌控全局

### Best for
知识型用户（战略顾问、市场分析人员），需要长时间阅读报告和对话，不喜欢界面太重太花哨。
