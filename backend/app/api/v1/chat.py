"""对话路由：发送消息（SSE 流式）、获取历史"""
import json
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from app.schemas.user import (
    ChatSendRequest,
    ConversationResponse,
    MessageResponse,
)
from app.core.deps import get_current_user
from app.services.db import db
from app.services.ai import chat_with_deepseek_stream

router = APIRouter()


@router.post("/send")
async def send_message(
    req: ChatSendRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """发送消息，返回 AI 流式回复（SSE 打字机效果）"""
    user_id = current_user.get("sub")

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

    # 获取或创建会话
    conversation = None
    if req.conversation_id:
        conversation = db.get_conversation(req.conversation_id)
        if not conversation or conversation.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在",
            )

    if not conversation:
        conversation = db.create_conversation(
            user_id=user_id,
            employee_id=req.employee_id,
        )

    # 保存用户消息
    db.add_message(conversation.id, "user", req.message)

    # 构建 SSE 流式响应
    async def event_generator():
        full_reply = ""
        try:
            async for chunk in chat_with_deepseek_stream(
                system_prompt=employee.system_prompt,
                messages=[
                    {"role": m["role"], "content": m["content"]}
                    for m in conversation.messages
                ],
            ):
                if await request.is_disconnected():
                    break
                full_reply += chunk
                yield {"event": "chunk", "data": json.dumps({"content": chunk})}

            # 保存 AI 回复
            if full_reply:
                db.add_message(conversation.id, "assistant", full_reply)

            # 发送完成事件
            yield {
                "event": "done",
                "data": json.dumps({
                    "conversation_id": conversation.id,
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
    current_user: dict = Depends(get_current_user),
):
    """获取当前用户的对话历史"""
    user_id = current_user.get("sub")
    conversations = db.list_conversations(user_id)

    return [
        ConversationResponse(
            id=conv.id,
            employee_id=conv.employee_id,
            messages=[
                MessageResponse(
                    role=m["role"],
                    content=m["content"],
                    timestamp=m["timestamp"],
                )
                for m in conv.messages
            ],
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )
        for conv in conversations
    ]
