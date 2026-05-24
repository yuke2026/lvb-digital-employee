## Variant: Command Center（指挥中心）

### Design stance
**深色 + 高密度 + 信息密集型** — 像 Linear/ Vercel Dashboard 那样，把所有关键状态摊开，让管理者一眼扫完不必点开。

### Key choices
- **Layout**: 三栏布局 — 左侧员工导航 → 中间对话区 → 右侧自动化任务面板。自动化面板常驻可见，不折叠。
- **Color**: 深色背景（#0f1117）+ 蓝色系强调色（#4f6ef7）。沿用当前产品深色基因。
- **Typography**: 系统字体，11-13px 为主，高密度信息。
- **Expert card**: 横向铺开专家信息（头像 + 名称 + 专长 + 状态标签），无需展开就知道谁在线。
- **Automation panel**: 任务列表+Toggle开关+最近执行记录，管理层看调度状态不用进子菜单。
- **Input**: 多行 textarea+快捷操作标签（生成报告、历史会话等），强调"任务入口"而非"聊天工具"。
- **Interactive**: Toggle 开关、Tab 切换、快捷按钮、消息发送、输入框回车发送、悬停状态。

### Trade-offs
- **Strong at**: 信息密度高、状态一览无遗、适合管理者快速决策
- **Weak at**: 视觉较重、聊天区域被压缩、页面元素较多

### Best for
权力型用户（CEO、高管），需要同时掌控对话和自动化状态，不愿在不同页面之间切换。
