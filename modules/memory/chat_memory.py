import re
import json
from typing import List, Optional
from redis.asyncio import Redis

# ✅ ไม่ clean ก่อนเก็บ เพื่อเก็บ raw
async def store_chat(redis_instance: Redis, user_id: int, message: dict) -> None:
    key = f"chat:{user_id}"
    await redis_instance.rpush(key, json.dumps(message))
    await redis_instance.expire(key, 86400)  # เก็บได้ 1 วัน (ปรับได้)

# ✅ ดึงแชทย้อนหลัง
async def get_chat_history(redis_instance: Redis, user_id: int, limit: int = 5) -> List[dict]:
    key = f"chat:{user_id}"
    raw_messages = await redis_instance.lrange(key, -limit, -1)
    return [json.loads(m) for m in raw_messages]

# ✅ สร้างบริบท (context) ส่งให้ GPT
async def build_chat_context(
    redis_instance: Redis,
    user_id: int,
    new_input: str,
    *,
    system_prompt: str,
    limit: int = 3
) -> List[dict]:
    messages = [{"role": "system", "content": system_prompt}]
    history = await get_chat_history(redis_instance, user_id, limit=limit)

    for entry in history:
        q = entry.get("question")
        r = entry.get("response")
        if q:
            messages.append({"role": "user", "content": q})
        if r:
            messages.append({"role": "assistant", "content": r})

    messages.append({"role": "user", "content": new_input})
    return messages

# ✅ ดึงข้อความล่าสุด (ใช้ตรวจ last question ได้)
async def get_previous_message(redis_instance: Redis, user_id: int) -> Optional[str]:
    key = f"chat:{user_id}"
    raw_messages = await redis_instance.lrange(key, -1, -1)
    if not raw_messages:
        return None

    try:
        last = json.loads(raw_messages[0])
        return last.get("question")
    except Exception:
        return None
