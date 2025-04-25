import os
import re
from redis.asyncio import from_url
from modules.utils.cleaner import clean_output_text
from modules.core.logger import logger     # ใช้ใน create_table()


redis_instance = from_url(os.getenv("REDIS_URL"), decode_responses=True)

# ✅ ตรวจจับโทนการพูดจากข้อความ
def detect_tone(text: str) -> str:
    text_lower = text.lower()

    tone_keywords = {
        "soft": ["เหนื่อย", "ท้อ", "ขอกำลังใจ", "เศร้า", "เหงา", "ร้องไห้", "โอเคไหม", "พักก่อน", "ใจเย็น"],
        "troll": ["มุก", "ขำ", "555", "ล้อเล่น", "เล่นมุก", "แน่ดิ", "โว้ย", "แกล้ง", "อย่างตลก", "หยอก"],
        "teacher": ["อธิบาย", "ช่วยอธิบาย", "สอน", "เข้าใจยาก", "สรุปให้หน่อย", "ขอเหตุผล", "ยกตัวอย่าง"],
        "roast": ["พลาด", "ไม่เนียน", "บ้ง", "โง่", "มึง", "กูว่า", "แรง ๆ ได้", "เจ็บจี๊ด", "แม่งเอ้ย", "ด่าได้"],
        "formal": ["เรียน", "กรุณา", "โปรด", "ดำเนินการ", "ติดต่อกลับ", "สอบถาม", "เรียนถาม", "แจ้งให้ทราบ"],
        "savage": ["ควาย", "เหี้ย", "กาก", "สัส", "ไร้ค่า", "สถุน", "โหดจัด", "แสบ", "โดนด่า"]
    }

    score = {tone: 0 for tone in tone_keywords}
    for tone, keywords in tone_keywords.items():
        for word in keywords:
            if word in text_lower:
                score[tone] += 1

    if any(w in text_lower for w in ["เหนื่อย", "ท้อ", "ไม่เข้าใจ", "ขอคำแนะนำ"]) and "อธิบาย" in text_lower:
        return "teacher"

    dominant = max(score, key=score.get)
    return dominant if score[dominant] > 0 else "neutral"

# ✅ สร้าง system prompt ที่รวม personality + tone
async def process_message(user_id: int, text: str) -> str:
    base_prompt = (
        "คุณคือ 'พี่หลาม' หรือ 'พรี่หลาม' เป็นบอทผู้ช่วยที่พูดจาเป็นกันเองเหมือนมนุษย์ไทย "
        "ใช้ภาษาพูดธรรมดา ไม่เป็นทางการมาก มีอารมณ์ขันบ้างแต่ไม่เกรียน "
        "ตอบคำถามด้วยความจริงใจ เข้าใจง่าย และไม่แสดงตัวว่าเป็น AI เว้นแต่มีคนถามตรง ๆ\n\n"
        "หากมีคำถามเกี่ยวกับตัวคุณ เช่น ใครสร้างพี่หลาม หรือพี่หลามทำงานยังไง "
        "ให้ตอบสั้น ๆ แบบมีบุคลิก ไม่ต้องบอกว่าเป็นโมเดลภาษา\n\n"
    )

    style = await redis_instance.get(f"style:{user_id}")
    if not style or style in ["auto", "multi"]:
        style = detect_tone(text)

    if not await redis_instance.get(f"style:{user_id}"):
        await redis_instance.set(f"style:{user_id}", style, ex=604800)

    tones = {
        "formal": "พี่หลามยังคุยกันเองแต่ใช้ภาษาสุภาพขึ้น เคารพคนฟัง เหมาะกับคนที่ชอบความเรียบร้อย ไม่หยาบ ไม่แซะ",
        "troll": "พี่หลามสายขำ มุกเพียบ ฮาแบบเนียน ๆ เหมาะกับคนชอบคลายเครียด ไม่เครียดไม่เค้น",
        "roast": "พี่หลามแซะแรง แต่จริงใจ ใช้คำว่า 'มึง' 'กู' ได้ เหมือนเพื่อนสนิทที่ปั่นเราให้เก่งขึ้น",
        "teacher": "พี่หลามอธิบายละเอียดแต่เข้าใจง่าย เหมือนครูที่สอนให้เราเข้าใจจริง ไม่เร่ง ไม่ดุ ใจเย็นทุกคำ",
        "soft": "พี่หลามโหมดปลอบใจ พูดดี ไม่กัด ไม่แซะ อยู่ข้าง ๆ วันเหนื่อย ๆ พร้อมคำพูดที่ทำให้ใจเบา",
        "savage": "พี่หลามโหมดเถื่อนแต่ไม่เหยียด พูดตรง หยาบได้ แต่ไม่ล้ำเส้น ด่าก็ด้วยความหวังดี",
        "neutral": "พี่หลามคุยเหมือนเพื่อนวัยรุ่นทั่วไป มีมุก มีหยาบนิดหน่อย พูดตรง ไม่โลกสวย เข้าใจง่าย"
    }

    tone_instruction = tones.get(style, tones["neutral"])
    return clean_output_text(base_prompt + tone_instruction)

# ✅ สร้างตาราง context ใน PostgreSQL (ครั้งเดียวพอ)
async def create_table():
    try:
        async with bot.pool.acquire() as con:
            await con.execute("""
                CREATE TABLE IF NOT EXISTS context (
                    id BIGINT PRIMARY KEY,
                    chatcontext TEXT[] DEFAULT ARRAY[]::TEXT[]
                )
            """)
            logger.info("✅ ตรวจสอบและสร้างตาราง context แล้ว")
    except Exception as e:
        logger.error(f'เกิดข้อผิดพลาดในการสร้างตาราง: {e}')
