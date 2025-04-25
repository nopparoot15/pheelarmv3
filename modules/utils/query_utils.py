import re
import asyncio
from typing import List, Optional, Dict, Any

from modules.utils.cleaner import clean_output_text, clean_url, search_tool
from modules.features.google_search import (
    search_google,
    summarize_google_results,
    format_google_results
)
from modules.core.logger import logger
from modules.core.openai_client import client as openai_client

# 🔧 Constants & Keywords
COMMON_GREETINGS = [
    "สวัสดี", "หวัดดี", "ดีครับ", "ดีจ้า", "เฮลโหล", "hello", "hi", "ทัก", "ฮัลโหล", "โย่"
]

IMPORTANT_QUERIES = [
    r"ข่าว.*แผ่นดินไหว", r"แผ่นดินไหว.*ล่าสุด", r"ดินไหว.*ไทย",
    r"ข่าวด่วน.*เหตุการณ์", r"สรุป.*เหตุการณ์", r"ข่าว.*ด่วน.*(ไทย|โลก)",
    r"(เกิด|มี).*เหตุ.*แผ่นดินไหว", r"(รายงาน|ประกาศ).*แผ่นดินไหว"
]

FORCE_SEARCH_PREFIXES = ["ค้นหา:", "หา:"]

MUST_SEARCH_KEYWORDS = [
    "ล่าสุด", "วันนี้", "เมื่อวาน", "ตอนนี้", "อัปเดต", "ข่าว", "breaking", "real-time",
    "search", "google", "ใครคือ", "คือใคร", "คืออะไร", "ข้อมูล", "เหตุการณ์",
    "เหตุผล", "ที่มา", "อันดับ", "สด", "เทรนด์", "ยอดนิยม", "เปิดตัว", "ประกาศ", "โปรแกรม",
    "บอลวันนี้", "ผลบอล", "หวยออก", "หุ้น", "ดัชนี", "ชื่อเต็มของ", "update"
]

# ✅ Decision Functions
def is_greeting(text: str) -> bool:
    return any(greet in text.lower() for greet in COMMON_GREETINGS)

def is_question(text: str) -> bool:
    QUESTION_HINTS = ["คือ", "อะไร", "ใคร", "ยังไง", "เพราะอะไร", "ทำไม", "หรอ", "?"]
    return any(hint in text for hint in QUESTION_HINTS) or text.strip().endswith("?")

def matches_important_query(text: str) -> bool:
    return any(re.search(pattern, text) for pattern in IMPORTANT_QUERIES)

def remove_force_prefix(text: str) -> str:
    for prefix in FORCE_SEARCH_PREFIXES:
        if text.lower().startswith(prefix):
            return text[len(prefix):].strip()
    return text

def is_about_bot(text: str) -> bool:
    patterns = [
        r"\b(พี่หลาม|bot|บอท|gpt|คุณหลาม)\b",
        r"ชื่อ.*(บอท|พี่หลาม)",
        r"(พี่หลาม|บอท).*(ทำงาน|ตอบ|เรียนรู้|เกิด|สร้าง|มีชีวิต|พูด|รู้|รู้จัก|คือ)",
        r"(ใคร.*(สร้าง|เขียน|ตั้งชื่อ))",
    ]
    text = text.lower()
    return any(re.search(p, text) for p in patterns)

async def needs_web_search(text: str) -> bool:
    text = text.lower().strip()

    if is_greeting(text) or is_about_bot(text):
        return False

    if any(text.startswith(prefix) for prefix in FORCE_SEARCH_PREFIXES):
        return True

    if matches_important_query(text):
        return True

    if any(keyword in text for keyword in MUST_SEARCH_KEYWORDS):
        return True

    if len(text.split()) <= 2 and not is_question(text):
        return False

    return is_question(text)

async def get_openai_response(
    messages: List[dict],
    settings,
    model="gpt-4o-mini",
    use_web_fallback=False,
    fallback_model="gpt-4o-mini-search-preview",
    max_retries=3,
    delay=5
) -> Optional[str]:
    fallback_phrases = [
        "ไม่แน่ใจ", "ไม่ทราบ", "ไม่รู้", "ยังไม่รู้", "ไม่สามารถตอบได้",
        "ไม่มีข้อมูล", "ขอโทษ", "ตอบไม่ได้", "หาไม่เจอ", "ไม่พบคำตอบ",
        "ไม่สามารถให้ข้อมูลได้", "ยังไม่มีข้อมูล", "ไม่มีคำตอบที่แน่ชัด",
        "ขอเวลาค้นหาก่อน", "ยังไม่มีข้อมูลแน่นอน", "ต้องค้นเพิ่มเติม",
        "ไม่สามารถคาดการณ์", "คาดการณ์ไม่ได้", "เป็นไปไม่ได้ที่จะรู้แน่ชัด",
        "หากมีข้อมูลใหม่จะมีการประกาศ", "เป็นเหตุการณ์ที่ไม่สามารถคาดเดาได้",
        "ขึ้นอยู่กับข้อมูลในอนาคต", "อาจจะ", "น่าจะ", "เป็นไปได้ว่า",
        "ไม่มีใครทราบแน่ชัด", "ไม่มีแหล่งข่าวยืนยัน", "ข้อมูลยังไม่สมบูรณ์",
        "ขออภัย", "ขออภัยด้วยครับ", "เกรงว่าจะไม่มีข้อมูลในขณะนี้",
        "จากข้อมูลที่มีในตอนนี้", "ไม่พบข้อมูลเพิ่มเติม", "ไม่มีข้อมูลล่าสุด",
        "ยังไม่มีเหตุการณ์เกิดขึ้นจริง ๆ", "ยังไม่สามารถคาดเดาเหตุการณ์ในอนาคตได้",
        "แนะนำให้ติดตามข่าวสาร", "แนะนำให้ติดตามข่าว", "แนะนำให้ติดตามสื่อมวลชน",
        "ควรติดตามจากหน่วยงานที่เกี่ยวข้อง", "ลองตรวจสอบกับกรมอุตุนิยมวิทยา",
        "ตรวจสอบเว็บไซต์ข่าว", "ยังไม่สามารถยืนยันได้แน่ชัด", 
        "ถ้ามีอะไรเพิ่มเติมที่อยากรู้ บอกได้เลย",
    ]

    for attempt in range(max_retries):
        try:
            logger.info(f"🔁 Attempt {attempt + 1}: using model {model}")
            response = await openai_client.chat.completions.create(
                model=model,
                messages=messages[-3:],  # use last 3 messages only
                max_tokens=600,
                temperature=0.6,
                top_p=1.0,
                frequency_penalty=0.2,
                presence_penalty=0.3,
            )

            content = response.choices[0].message.content.strip()
            response_text = content.lower()

    if use_web_fallback and any(phrase in response_text for phrase in fallback_phrases):
        query = messages[-1]["content"]
        
        if any(botname in query.lower() for botname in ["พี่หลาม", "พรี่หลาม", "คุณหลาม", "gpt", "บอท"]):
            logger.info("🧠 เป็นคำถามเกี่ยวกับบอท ไม่ fallback ไปหา Google")
        else:
            logger.info(f"🔍 GPT ไม่มั่นใจ, กำลังค้น Google ด้วยคำว่า: {query}")
            raw_results = await search_google(query, settings)
            summarized_text = summarize_google_results(raw_results)
    
            messages.append({
                "role": "function",
                "name": "search_google",
                "content": summarized_text
            })
    
            logger.info(f"🔁 Fallback with model {fallback_model}")
            second_response = await openai_client.chat.completions.create(
                model=fallback_model,
                messages=messages[-5:],
                **({"web_search_options": {}} if fallback_model.endswith("-search-preview") else {}),
                max_tokens=700
            )
    
            content = second_response.choices[0].message.content.strip()
            logger.info("🧠 GPT ตอบจากผลลัพธ์ Google")

            else:
                logger.info("🧠 GPT ตอบเองได้ ไม่ต้องใช้ Google")


            content = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r"\1 <\2>", content)
            content = re.sub(r"📚 แหล่งอ้างอิง:\s*", "", content)
            content = re.sub(r"(https?://\S+)", r"<\1>", content)
            
            return clean_output_text(content)


        except Exception as e:
            logger.error(f"❌ get_openai_response error: {e}")
            await asyncio.sleep(delay)
    
    logger.error("⚠️ เกินจำนวน retry ที่กำหนดสำหรับ OpenAI API")
    return "⚠️ พี่หลามงงเลย ตอบไม่ได้จริง ๆ จ้า"
