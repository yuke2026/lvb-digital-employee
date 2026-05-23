"""DeepSeek Embedding 服务"""
import httpx
from app.core.config import settings


async def get_embedding(text: str) -> list[float]:
    """获取单条文本的 embedding 向量 (1536维)"""
    api_key = settings.DEEPSEEK_API_KEY
    if not api_key:
        raise ValueError("DeepSeek API 密钥未配置，请设置 DEEPSEEK_API_KEY")

    url = f"{settings.DEEPSEEK_BASE_URL}/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.DEEPSEEK_EMBEDDING_MODEL,
        "input": text,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"DeepSeek API 错误 ({e.response.status_code}): {e.response.text[:200]}")
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"DeepSeek API 响应格式错误: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"请求 DeepSeek API 异常: {str(e)}")


async def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """批量获取文本的 embedding 向量列表"""
    if not texts:
        return []

    api_key = settings.DEEPSEEK_API_KEY
    if not api_key:
        raise ValueError("DeepSeek API 密钥未配置，请设置 DEEPSEEK_API_KEY")

    url = f"{settings.DEEPSEEK_BASE_URL}/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.DEEPSEEK_EMBEDDING_MODEL,
        "input": texts,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"DeepSeek API 错误 ({e.response.status_code}): {e.response.text[:200]}")
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"DeepSeek API 响应格式错误: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"请求 DeepSeek API 异常: {str(e)}")
