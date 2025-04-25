from typing import Optional
from modules.core.logger import logger
from modules.core.openai_client import client
from modules.utils.cleaner import clean_output_text

# ✅ สรุปข้อความทั่วไปด้วย GPT
async def summarize_with_gpt(text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "สรุปข้อความให้สั้น กระชับ ไม่เกิน 3-4 ประโยค "
                "ใช้ภาษาพูดที่เข้าใจง่าย เป็นกันเอง"
            )
        },
        {
            "role": "user",
            "content": f"สรุปเนื้อหานี้ให้หน่อย:\n{text}"
        }
    ]

    try:
        logger.info("🔮 เริ่มสรุปข้อความด้วย GPT")
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )
        result = response.choices[0].message.content.strip()
        return clean_output_text(result)
    except Exception as e:
        logger.error(f"❌ สรุปข้อความด้วย GPT ล้มเหลว: {e}")
        return "⚠️ พี่หลามสรุปไม่ได้ตอนนี้ ขออภัยจ้า"

# ✅ สรุปคำทำนายไพ่ยิปซีแบบกระชับ โดยใช้ GPT
async def summarize_tarot_reading(text: str, topic: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "คุณคือแม่หมอดูไพ่ยิปซี ตอบคำทำนายกระชับ ตรงประเด็น จริงใจ "
                "ใช้ภาษาเข้าใจง่าย เป็นกันเอง ไม่ยาวเกิน 4-5 บรรทัด "
                "พร้อมสรุปข้อควรระวังที่เหมาะสมกับหัวข้อนั้น ๆ"
            )
        },
        {
            "role": "user",
            "content": (
                f"หัวข้อ: {topic}\n\n"
                f"ไพ่ที่ได้และความหมาย:\n{text}\n\n"
                "ช่วยสรุปภาพรวมให้เข้าใจง่าย พร้อมข้อควรระวังแบบกลาง ๆ"
            )
        }
    ]

    try:
        logger.info(f"🔮 เริ่มสรุปคำทำนายไพ่ยิปซี หัวข้อ: '{topic}' ด้วย GPT")
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=500,
            temperature=0.6
        )
        result = response.choices[0].message.content.strip()
        return clean_output_text(result)
    except Exception as e:
        logger.error(f"❌ สรุปคำทำนายไพ่ยิปซีด้วย GPT ล้มเหลว: {e}")
        return "⚠️ แม่หมอขอพักแป๊บนึง ลองใหม่อีกครั้งนะลูก"
