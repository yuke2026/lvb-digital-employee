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
