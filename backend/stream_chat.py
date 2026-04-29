"""流式输出接口

接收自然语言查询，调用 LLM API 流式返回 SSE 响应。
"""
import asyncio
import json
import logging
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------- 配置 ----------

LLM_API_BASE = "https://api.deepseek.com/v1"
LLM_API_KEY = "sk-your-key-here"  # 从环境变量读取
LLM_MODEL = "deepseek-v4-flash"
LLM_TIMEOUT = 30.0  # API 调用超时

# ---------- 请求模型 ----------

class ChatRequest(BaseModel):
    query: str
    stream: bool = True


# ---------- 流式 SSE 生成器 ----------

def _build_messages(query: str) -> list[dict]:
    """构建 LLM 消息"""
    return [
        {
            "role": "system",
            "content": "你是一个有用的AI助手。请用中文回答用户问题。",
        },
        {"role": "user", "content": query},
    ]


async def _stream_llm(
    query: str,
) -> AsyncGenerator[str, None]:
    """
    调用 LLM API 并逐块生成 SSE 事件。

    生成的事件格式：
      data: {"type": "chunk", "content": "..."}
      data: {"type": "done", "content": ""}
      data: {"type": "error", "content": "错误信息"}

    设计选择：
    - 使用 httpx.AsyncClient 而非 requests，避免阻塞事件循环
    - 超时通过 asyncio.wait_for 包裹，超时时向前端发送 error 事件而非直接崩溃
    - API 错误（401/429）在流开始前抛出 HTTPException，流开始后通过 error 事件通知
    """
    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        try:
            # 发起流式请求，使用 asyncio.wait_for 实现超时控制
            async with asyncio.wait_for(
                client.post(
                    f"{LLM_API_BASE}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {LLM_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": LLM_MODEL,
                        "messages": _build_messages(query),
                        "stream": True,
                    },
                ),
                timeout=LLM_TIMEOUT,
            ) as resp:
                # 处理 API 层面错误（流开始前）
                if resp.status_code == 401:
                    yield f"data: {json.dumps({'type': 'error', 'content': 'API 认证失败，请检查 API Key'})}\n\n"
                    return
                if resp.status_code == 429:
                    yield f"data: {json.dumps({'type': 'error', 'content': '请求过于频繁，请稍后重试'})}\n\n"
                    return
                if resp.status_code >= 400:
                    yield f"data: {json.dumps({'type': 'error', 'content': f'API 返回错误: HTTP {resp.status_code}'})}\n\n"
                    return

                # 逐行解析 SSE 流
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    payload = line[6:]  # 去掉 "data: " 前缀
                    if payload == "[DONE]":
                        break

                    try:
                        chunk = json.loads(payload)
                        delta = (
                            chunk.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                        if delta:
                            yield f"data: {json.dumps({'type': 'chunk', 'content': delta})}\n\n"
                    except json.JSONDecodeError:
                        continue

        except asyncio.TimeoutError:
            # 超时：通过 error 事件通知前端，不崩溃
            yield f"data: {json.dumps({'type': 'error', 'content': 'API 响应超时（超过 30 秒），请简化问题后重试'})}\n\n"
            return
        except httpx.ConnectError:
            yield f"data: {json.dumps({'type': 'error', 'content': '无法连接到 API 服务，请检查网络'})}\n\n"
            return
        except Exception as e:
            logger.exception("LLM 流式调用异常")
            yield f"data: {json.dumps({'type': 'error', 'content': f'服务器内部错误: {str(e)}'})}\n\n"
            return

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


# ---------- 路由 ----------

def register_routes(app: FastAPI):
    """注册流式接口路由"""

    @app.post("/api/chat/stream")
    async def chat_stream(req: ChatRequest):
        """
        流式对话接口（SSE）

        请求：
          POST /api/chat/stream
          {"query": "2024年最畅销的产品是什么？"}

        响应（SSE 事件流）：
          data: {"type": "chunk", "content": "2024年最畅销的产品是..."}
          data: {"type": "chunk", "content": "苹果 iPhone 16 Pro..."}
          data: {"type": "done"}  # 或 {"type": "error", "content": "..."}
        """
        if not req.query.strip():
            raise HTTPException(400, "查询内容不能为空")

        # 使用 media_type="text/event-stream" 告知浏览器这是 SSE
        return StreamingResponse(
            _stream_llm(req.query),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
            },
        )
