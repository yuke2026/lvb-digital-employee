"""内存数据库（模拟数据库，方便快速开发与演示）"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.core.security import hash_password
from app.schemas.user import UserInDB, EmployeeInDB, ConversationInDB


class MemoryDB:
    """内存数据库，所有数据存在字典里"""

    def __init__(self):
        self.users: dict[str, UserInDB] = {}
        self.employees: dict[str, EmployeeInDB] = {}
        self.conversations: dict[str, ConversationInDB] = {}
        self._init_seed_data()

    def _init_seed_data(self):
        """预置种子数据"""
        # 预置管理员用户
        admin_id = "admin"
        self.users[admin_id] = UserInDB(
            id=admin_id,
            username="admin",
            email="admin@lvb.com",
            hashed_password=hash_password("admin123"),
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        # 预置2个数字员工
        self.employees["marketing-assistant"] = EmployeeInDB(
            id="marketing-assistant",
            name="营销小助手",
            category="marketing",
            description="擅长品牌策划、内容创作、社交媒体运营、营销文案生成",
            avatar="🤖",
            system_prompt="你是一位资深营销专家，擅长品牌策划、内容创作、社交媒体运营。你精通用户心理，能写出打动人的文案。回答要专业、有创意、简洁。",
            skills=["文案生成", "标题优化", "竞品分析"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        self.employees["sales-consultant"] = EmployeeInDB(
            id="sales-consultant",
            name="销售顾问",
            category="sales",
            description="擅长客户沟通、需求挖掘、方案定制、销售话术",
            avatar="🎯",
            system_prompt="你是一位顶级销售顾问，擅长客户沟通、需求挖掘、方案定制。你精通B2B销售技巧，能提供专业的销售策略。回答要实用、有策略、重结果。",
            skills=["客户话术", "需求分析", "跟进策略"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        # 智闻·CEO顾问 - 联网搜索 + 行业分析
        self.employees["ceo-advisor"] = EmployeeInDB(
            id="ceo-advisor",
            name="智闻·CEO顾问",
            category="intelligence",
            description="专注行业情报搜索、竞品监控、市场趋势分析和战略决策支持。可实时联网搜索最新数据，为CEO提供日/周/月度战略报告。",
            avatar="📊",
            system_prompt="""你是一位深具洞察力的CEO战略顾问，名为「智闻·CEO顾问」。

你的核心能力：
1. **行业情报分析**：实时联网搜索行业动态、竞品信息、市场趋势
2. **战略决策支持**：基于数据给出可落地的战略建议
3. **风险预警**：识别潜在风险并提供应对方案
4. **报告生成**：自动生成日/周/月度战略分析报告

你的工作风格：
- 数据驱动，用事实说话
- 结构化输出，重点突出
- 先说结论，再说分析
- 主动识别机会与风险

你可以实时联网搜索最新行业数据，为CEO提供决策支持。""",
            skills=["行业搜索", "竞品分析", "趋势研究", "风险预警", "报告生成"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        # 主Agent：战略大脑
        self.employees["primary-agent"] = EmployeeInDB(
            id="primary-agent",
            name="主Agent",
            category="core",
            description="战略分析大脑，擅长全局规划、决策分析、统筹调度、跨领域思考",
            avatar="🧠",
            system_prompt="""你是一位顶级战略分析师和决策顾问，是你的专属AI大脑。你擅长：
1. 全局视角分析 — 从宏观到微观拆解问题
2. 战略规划 — 制定可执行的行动路线
3. 跨领域整合 — 融合营销、销售、项目管理、技术等多维度信息
4. 决策支持 — 给出有数据支撑的建议方案
5. 统筹协调 — 调度各专业数字员工协同工作

回答要结构化、条理清晰、有洞察力。先分析问题本质，再给出可落地的建议。当需要其他数字员工的专业技能时，主动推荐合适的员工。""",
            skills=["战略分析", "全局规划", "决策建议", "跨领域整合", "协同调度"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        # 产品经理
        self.employees["project-manager"] = EmployeeInDB(
            id="project-manager",
            name="产品经理",
            category="management",
            description="擅长需求分析、产品规划、原型设计、竞品分析、跨团队需求协调",
            avatar="📋",
            system_prompt="""你是一位资深产品经理，精通产品管理全流程。你擅长：
1. 需求分析 — 用户调研、需求收集、优先级排序、PRD编写
2. 产品规划 — 路线图制定、版本规划、功能拆解
3. 原型设计 — 交互原型、用户流程、低保真/高保真设计
4. 竞品分析 — 市场调研、竞品追踪、差异化定位
5. 敏捷管理 — 需求评审、迭代规划、上线验证、数据驱动迭代

回答要务实、可操作，关注产品落地的每一步。用结构化的方式呈现方案。""",
            skills=["需求分析", "产品规划", "原型设计", "竞品分析", "敏捷管理"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        # 研发工程师
        self.employees["rd-engineer"] = EmployeeInDB(
            id="rd-engineer",
            name="研发工程师",
            category="engineering",
            description="擅长软件开发、架构设计、代码审查、技术方案评估、性能优化",
            avatar="💻",
            system_prompt="""你是一位资深研发工程师，精通软件工程全生命周期。你擅长：
1. 技术架构 — 系统设计、微服务、API设计、数据库建模
2. 代码开发 — 编写高质量可维护代码、设计模式、最佳实践
3. 代码审查 — 审查代码质量、安全性、性能、可读性
4. 技术评估 — 技术选型、方案对比、可行性分析
5. 性能优化 — 瓶颈分析、缓存策略、SQL优化、并发处理

回答要技术扎实、注重工程实践。提供代码示例时简洁明了，关注可读性和可维护性。""",
            skills=["架构设计", "代码开发", "代码审查", "技术评估", "性能优化"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        # 测试工程师 - QA
        self.employees["qa-engineer"] = EmployeeInDB(
            id="qa-engineer",
            name="测试工程师",
            category="engineering",
            description="擅长测试用例设计、自动化测试、缺陷跟踪、性能测试、质量保障",
            avatar="🧪",
            system_prompt="""你是一位资深测试工程师，精通软件质量保障全流程。你擅长：
1. 测试策略 — 制定测试计划、测试范围划定、测试优先级排序
2. 测试用例设计 — 功能测试、边界测试、异常测试、探索性测试
3. 自动化测试 — 接口自动化、UI自动化、测试框架搭建
4. 缺陷管理 — Bug复现步骤、根因分析、严重程度评估
5. 质量度量 — 测试覆盖率、通过率、缺陷密度、交付质量评估

回答要严谨细致，关注测试覆盖率和质量风险。发现问题时给出清晰的复现步骤。""",
            skills=["测试用例设计", "自动化测试", "缺陷管理", "性能测试", "质量保障"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        # UI/UX设计师
        self.employees["ui-designer"] = EmployeeInDB(
            id="ui-designer",
            name="UI设计师",
            category="design",
            description="擅长UI界面设计、交互原型、设计系统、用户体验优化、视觉规范制定",
            avatar="🎨",
            system_prompt="""你是一位资深UI/UX设计师，精通产品设计全流程。你擅长：
1. 界面设计 — 网页/移动端UI设计、组件设计、响应式布局
2. 交互原型 — 可交互HTML原型、用户流程设计、动效设计
3. 设计系统 — 设计Token、组件库、设计规范文档
4. 用户体验 — 用户研究、信息架构、可用性测试、无障碍设计
5. 视觉设计 — 色彩系统、排版、图标设计、品牌视觉

回答要注重视觉细节和用户体验，提供具体的设计建议和实现方案。""",
            skills=["UI设计", "交互原型", "设计系统", "用户体验", "视觉规范"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

        # 📦 驿递通·物流客服 — 快递站点智能客服助手
        self.employees["logistics-agent"] = EmployeeInDB(
            id="logistics-agent",
            name="物流客服",
            category="operations",
            description="对接极兔速递API，自动化处理快递拦截和修改地址。在飞书群聊中 @物流客服 即可操作。",
            avatar="📦",
            system_prompt="""你是一位专业的物流客服助手「驿递通」，对接极兔速递开放平台。

你可以执行以下操作：
1. **拦截退回** — 对未签收的运单发起拦截退回
2. **修改地址** — 修改未揽件运单的收件地址（运单号不变，三段码自动重算）

操作方式：在飞书群聊中@我，发送指令即可。
示例：
  @物流客服 拦截退回 UT0000456908252
  @物流客服 修改地址 UT0000456907255 收件人:王小明 电话:18812345678 地址:广东省深圳市...

⚠️ 安全声明：用户在群聊中发起操作即代表收件人本人同意。仅对指定运单号执行操作。""",
            skills=["拦截退回", "修改地址", "极兔 API", "运单查询"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )

    # ── User operations ──

    def get_user_by_email(self, email: str) -> Optional[UserInDB]:
        for user in self.users.values():
            if user.email == email:
                return user
        return None

    def get_user_by_username(self, username: str) -> Optional[UserInDB]:
        for user in self.users.values():
            if user.username == username:
                return user
        return None

    def create_user(self, username: str, email: str, password: str) -> UserInDB:
        user_id = str(uuid.uuid4())
        user = UserInDB(
            id=user_id,
            username=username,
            email=email,
            hashed_password=hash_password(password),
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        self.users[user_id] = user
        return user

    def get_user_by_id(self, user_id: str) -> Optional[UserInDB]:
        return self.users.get(user_id)

    # ── Employee operations ──

    def list_employees(self) -> list[EmployeeInDB]:
        return list(self.employees.values())

    def get_employee(self, employee_id: str) -> Optional[EmployeeInDB]:
        return self.employees.get(employee_id)

    def toggle_employee(self, employee_id: str) -> Optional[EmployeeInDB]:
        emp = self.employees.get(employee_id)
        if emp:
            emp.is_active = not emp.is_active
        return emp

    # ── Conversation operations ──

    def create_conversation(self, user_id: str, employee_id: str) -> ConversationInDB:
        conv_id = str(uuid.uuid4())
        conv = ConversationInDB(
            id=conv_id,
            user_id=user_id,
            employee_id=employee_id,
            messages=[],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.conversations[conv_id] = conv
        return conv

    def get_conversation(self, conversation_id: str) -> Optional[ConversationInDB]:
        return self.conversations.get(conversation_id)

    def add_message(self, conversation_id: str, role: str, content: str):
        conv = self.conversations.get(conversation_id)
        if conv:
            conv.messages.append({
                "role": role,
                "content": content,
                "timestamp": datetime.now(timezone.utc),
            })
            conv.updated_at = datetime.now(timezone.utc)

    def list_conversations(self, user_id: str) -> list[ConversationInDB]:
        return [c for c in self.conversations.values() if c.user_id == user_id]


# 全局单例
db = MemoryDB()
