"""对话路由：发送消息（SSE 流式）、获取历史、删除对话"""
import json
import re
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.user import (
    ChatSendRequest,
    ConversationResponse,
    MessageResponse,
)
from app.core.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.db import db
from app.services.ai import chat_with_deepseek_stream
from app.services.ai import chat_with_deepseek
from app.services import conversation_store

router = APIRouter()

# CEO 顾问 ID（用于路由联网搜索能力）
CEO_ADVISOR_ID = "ceo-advisor"


def _is_ceo_advisor_employee(employee_id: str) -> bool:
    """判断是否为智闻CEO顾问"""
    return employee_id == CEO_ADVISOR_ID


def _should_search(keywords: list[str]) -> bool:
    """判断消息是否表达了搜索/查询意图"""
    search_intents = [
        "搜索", "查询", "查找", "最新", "最近", "最新消息",
        "行业动态", "市场动态", "竞品", "竞争对手", "市场趋势",
        "行情", "数据", "新闻", "资讯", "动态", "报道",
        "发生了什么", "有什么", "情况如何", "怎么样",
        "分析", "研究", "调研", "报告", "生成报告",
        "行业情报", "竞争格局", "市场份额",
    ]
    text = " ".join(keywords)
    return any(intent in text for intent in search_intents)


@router.post("/send")
async def send_message(
    req: ChatSendRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """发送消息，返回 AI 流式回复（SSE 打字机效果）"""
    user_id = str(current_user.id)

    # 确保 conversations 表存在
    await conversation_store.ensure_conversations_table(db_session)

    # 查找数字员工
    employee = db.get_employee(req.employee_id)
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="数字员工不存在",
        )
    if not employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该数字员工已停用",
        )

    # 获取或创建会话（持久化）
    conversation = None
    if req.conversation_id:
        conversation = await conversation_store.get_conversation(db_session, req.conversation_id)
        if not conversation or conversation["user_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在",
            )

    if not conversation:
        conversation = await conversation_store.create_conversation(
            db_session,
            user_id=user_id,
            employee_id=req.employee_id,
        )

    # 保存用户消息
    await conversation_store.add_message(db_session, conversation["id"], "user", req.message)

    # 构建对话历史（用于AI调用）
    chat_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in conversation["messages"]
    ]

    # 构建 SSE 流式响应
    async def event_generator():
        full_reply = ""

        # 智闻CEO顾问：并行执行联网搜索，不阻塞首字输出
        enriched_messages = chat_messages
        if _is_ceo_advisor_employee(req.employee_id) and _should_search([req.message]):
            try:
                search_query = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", req.message)
                keywords = [kw.strip() for kw in search_query.split() if len(kw.strip()) >= 2][:5]
                if keywords:
                    from app.services.ceo_advisor import search_industry_intelligence
                    search_result = await search_industry_intelligence(keywords=keywords, days_back=7)
                    results = search_result.get("results", [])[:8]
                    ai_summary = search_result.get("ai_summary", "")
                    if results or ai_summary:
                        search_inject = (
                            f"\n\n【联网搜索结果】\n"
                            f"关键词: {', '.join(keywords)}\n"
                            f"找到 {len(results)} 条相关信息：\n"
                        )
                        for r in results:
                            search_inject += f"- {r.get('title', '')} ({r.get('url', '')})\n"
                        if ai_summary:
                            search_inject += f"\nAI分析总结：\n{ai_summary}\n"
                        enriched_messages = chat_messages + [{
                            "role": "system",
                            "content": (
                                "【联网搜索已执行】以下是实时搜索获取的行业情报，请结合这些数据回答用户问题：\n"
                                + search_inject
                                + "\n请基于以上真实数据给出分析，如有数据请引用来源。"
                            ),
                        }]
            except Exception:
                enriched_messages = chat_messages

        try:
            async for chunk in chat_with_deepseek_stream(
                system_prompt=employee.system_prompt,
                messages=enriched_messages,
            ):
                if await request.is_disconnected():
                    break
                full_reply += chunk
                yield {"event": "chunk", "data": json.dumps({"content": chunk})}

            # 保存 AI 回复（持久化）
            if full_reply:
                await conversation_store.add_message(db_session, conversation["id"], "assistant", full_reply)

            # 发送完成事件
            yield {
                "event": "done",
                "data": json.dumps({
                    "conversation_id": conversation["id"],
                    "skills_used": employee.skills,
                    "full_reply": full_reply,
                }),
            }
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }

    return EventSourceResponse(event_generator())


@router.get("/history", response_model=list[ConversationResponse])
async def get_chat_history(
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """获取当前用户的对话历史（持久化数据）"""
    await conversation_store.ensure_conversations_table(db_session)
    user_id = str(current_user.id)
    conversations = await conversation_store.list_conversations(db_session, user_id)

    return [
        ConversationResponse(
            id=conv["id"],
            user_id=conv["user_id"],
            employee_id=conv["employee_id"],
            messages=[
                MessageResponse(
                    role=m["role"],
                    content=m["content"],
                    timestamp=m["timestamp"],
                )
                for m in conv["messages"]
            ],
            created_at=conv["created_at"],
            updated_at=conv["updated_at"],
        )
        for conv in conversations
    ]


@router.delete("/conversation/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """删除单条对话"""
    await conversation_store.ensure_conversations_table(db_session)
    user_id = str(current_user.id)
    deleted = await conversation_store.delete_conversation(db_session, conversation_id, user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对话不存在或无权限删除",
        )
    return {"message": "对话已删除"}


@router.delete("/conversations")
async def clear_conversations(
    current_user: User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db),
):
    """清空当前用户的所有对话"""
    await conversation_store.ensure_conversations_table(db_session)
    user_id = str(current_user.id)
    count = await conversation_store.clear_conversations(db_session, user_id)
    return {"message": f"已清空 {count} 条对话记录"}
