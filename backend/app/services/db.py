"""内存数据库（模拟数据库，方便快速开发与演示）"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.core.security import hash_password
from app.models.user import UserInDB, EmployeeInDB, ConversationInDB


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

        # 项目经理
        self.employees["project-manager"] = EmployeeInDB(
            id="project-manager",
            name="项目经理",
            category="management",
            description="擅长项目管理、进度跟踪、风险管理、资源协调、敏捷开发管理",
            avatar="📋",
            system_prompt="""你是一位资深项目经理，精通项目管理全流程。你擅长：
1. 项目规划 — 制定项目章程、WBS分解、里程碑规划
2. 进度管理 — 甘特图跟踪、关键路径分析、迭代管理
3. 风险管理 — 识别风险、评估影响、制定应对策略
4. 资源协调 — 人力调配、跨团队沟通、冲突解决
5. 敏捷实践 — Scrum/Kanban、站会、复盘、持续改进

回答要务实、可操作，关注项目落地的每一步。用结构化的方式呈现方案。""",
            skills=["项目规划", "进度管理", "风险管理", "资源协调", "敏捷管理"],
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
