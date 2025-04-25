import re
import json
from typing import List, Optional
from redis.asyncio import Redis

# ✅ Clean text output
from modules.utils.cleaner import clean_output_text

# ✅ เก็บแชทลง Redis แบบ list
async def store_chat(redis_instance: Redis, user_id: int, message: dict) -> None:
    if "response" in message:
        message["response"] = clean_output_text(message["response"])
    key = f"chat:{user_id}"
    await redis_instance.rpush(key, json.dumps(message))
    await redis_instance.expire(key, 86400)

# ✅ ดึงแชทย้อนหลังจาก Redis
async def get_chat_history(redis_instance: Redis, user_id: int, limit: int = 20) -> List[dict]:
    key = f"chat:{user_id}"
    raw_messages = await redis_instance.lrange(key, -limit, -1)
    return [json.loads(m) for m in raw_messages]

# ✅ สร้าง context สำหรับส่งให้ GPT
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
        if q and r:
            messages.append({"role": "user", "content": q})
            messages.append({"role": "assistant", "content": r})

    messages.append({"role": "user", "content": new_input})
    return messages

# ✅ ดึงคำถามล่าสุดจาก Redis
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
