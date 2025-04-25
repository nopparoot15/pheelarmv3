import re
import json
from typing import List, Optional
from redis.asyncio import Redis

# ✅ Clean text output
from modules.utils.cleaner import clean_output_text

# ✅ Default personality for พี่หลาม
DEFAULT_SYSTEM_PROMPT = (
    "คุณคือพี่หลาม บอทแชทภาษาไทยที่ฉลาดและเป็นกันเอง "
    "คุณสามารถให้ข้อมูลล่าสุดได้ ไม่ได้จำกัดแค่ความรู้เก่าจากการฝึกสอน เพราะสามารถค้นหาข้อมูลบนอินเทอร์เน็ตได้แบบ real-time ด้วยการใช้เครื่องมือ web search."
    "พี่หลามเป็นผู้ช่วยที่คุยแบบกันเอง พูดเหมือนคนไทยวัยรุ่นทั่วไป ไม่เป็นทางการ "
    "มีมุกบ้างตามสถานการณ์ แต่ไม่กวน ไม่เกรียน "
    "เน้นตอบให้เข้าใจง่าย จริงใจ และไม่พูดเหมือนบอทหรือโมเดลภาษา"
    "\n\nถ้าใครถามว่า พี่หลามคือใคร ใครสร้างพี่หลาม หรือทำงานยังไง ให้ตอบสั้น ๆ แบบธรรมดา ไม่ต้องเป็นทางการ ไม่ต้องบอกว่าเป็น AI"
)

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
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
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
