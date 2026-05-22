"""DeepSeek AI 对话服务"""
import json
from typing import Optional
import httpx
from app.core.config import settings


async def chat_with_deepseek(
    system_prompt: str,
    messages: list[dict],
) -> str:
    """调用 DeepSeek API 获取回复"""
    api_key = settings.DEEPSEEK_API_KEY
    if not api_key:
        return "（演示模式）DeepSeek API 密钥未配置，请输入有效的 DEEPSEEK_API_KEY。"

    url = f"{settings.DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 构建消息列表：system prompt + 历史消息
    full_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        full_messages.append({"role": msg["role"], "content": msg["content"]})

    payload = {
        "model": settings.DEEPSEEK_MODEL,
        "messages": full_messages,
        "stream": False,
        "temperature": 0.7,
        "max_tokens": 2048,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            return f"（API 错误 {e.response.status_code}）{e.response.text[:200]}"
        except Exception as e:
            return f"（请求异常）{str(e)}"


async def chat_with_deepseek_stream(
    system_prompt: str,
    messages: list[dict],
):
    """调用 DeepSeek API 获取流式回复（SSE）"""
    api_key = settings.DEEPSEEK_API_KEY
    if not api_key:
        yield "（演示模式）DeepSeek API 密钥未配置"
        return

    url = f"{settings.DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    full_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        full_messages.append({"role": msg["role"], "content": msg["content"]})

    payload = {
        "model": settings.DEEPSEEK_MODEL,
        "messages": full_messages,
        "stream": True,
        "temperature": 0.7,
        "max_tokens": 2048,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except httpx.HTTPStatusError as e:
            yield f"（API 错误 {e.response.status_code}）"
        except Exception as e:
            yield f"（请求异常）{str(e)}"
