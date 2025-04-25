# 🔹 Standard Library
import os
import json
import asyncio
import random
import re
from datetime import datetime
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

# 🔹 Third-Party Packages
import asyncpg
import discord
import pytz
import openai
import httpx
import requests
import redis.asyncio as redis
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

# 🔹 Local Modules
from modules.features.oil_price import get_oil_price_today
from modules.features.gold_price import get_gold_price_today
from modules.features.lottery_checker import get_lottery_results
from modules.features.exchange_rate import get_exchange_rate
from modules.features.weather_forecast import get_weather
from modules.features.daily_news import get_daily_news
from modules.features.global_news import get_global_news
from modules.features.google_search import search_google, search_image
from modules.tarot.tarot_reading import draw_cards_and_interpret_by_topic
from modules.nlp.message_matcher import match_topic
from modules.memory.chat_memory import store_chat, build_chat_context, get_chat_history
from modules.utils.cleaner import clean_output_text, search_tool, format_response_markdown, clean_url
from modules.utils.thai_to_eng_city import convert_thai_to_english_city
from modules.utils.thai_datetime import get_thai_datetime_now, format_thai_datetime
from modules.utils.query_utils import (
    is_greeting, is_about_bot, is_question,
    matches_important_query, remove_force_prefix,
    needs_web_search
)
from modules.core.logger import logger
from modules.core.openai_client import client as openai_client
from modules.utils.query_utils import get_openai_response
from modules.personality.tone_manager import detect_tone

# ✅ Load environment variables
load_dotenv()

class Settings(BaseSettings):
    DISCORD_TOKEN: str = Field(..., env='DISCORD_TOKEN')
    OPENAI_API_KEY: str = Field(..., env='OPENAI_API_KEY')
    DATABASE_URL: Optional[str] = Field(None, env='DATABASE_URL')
    PG_USER: Optional[str] = Field(None, env='PGUSER')
    PG_PW: Optional[str] = Field(None, env='PGPASSWORD')
    PG_HOST: Optional[str] = Field(None, env='PGHOST')
    PG_PORT: str = Field('5432', env='PGPORT')
    PG_DB: Optional[str] = Field(None, env='PGDATABASE')
    GOOGLE_API_KEY: Optional[str] = Field(None, env='GOOGLE_API_KEY')
    GOOGLE_CSE_ID: Optional[str] = Field(None, env='GOOGLE_CSE_ID')
    REDIS_URL: str = Field('redis://localhost', env='REDIS_URL')

settings = Settings()

CHANNEL_ID = 1350812185001066538
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="$", intents=intents)
openai.api_key = settings.OPENAI_API_KEY
redis_instance = None

async def setup_connection():
    global redis_instance
    for _ in range(3):
        try:
            redis_instance = await redis.from_url(settings.REDIS_URL, decode_responses=True)
            await redis_instance.ping()
            logger.info("✅ Redis connected")
            break
        except Exception as e:
            logger.warning(f"🔁 Redis retry failed: {e}")
            await asyncio.sleep(2)
    else:
        logger.error("❌ Redis connection failed")
        redis_instance = None

    try:
        if settings.DATABASE_URL:
            bot.pool = await asyncpg.create_pool(settings.DATABASE_URL)
        else:
            bot.pool = await asyncpg.create_pool(
                user=settings.PG_USER,
                password=settings.PG_PW,
                host=settings.PG_HOST,
                port=settings.PG_PORT,
                database=settings.PG_DB
            )
        logger.info("✅ PostgreSQL connected")
    except Exception as e:
        logger.error(f"❌ PostgreSQL connection failed: {e}")
        bot.pool = None

async def create_table():
    try:
        async with bot.pool.acquire() as con:
            await con.execute("""
                CREATE TABLE IF NOT EXISTS context (
                    id BIGINT PRIMARY KEY,
                    chatcontext TEXT[] DEFAULT ARRAY[]::TEXT[]
                )
            """)
            logger.info("✅ context table ensured")
    except Exception as e:
        logger.error(f"❌ create_table error: {e}")

async def process_message(user_id: int, text: str) -> str:
    style = await redis_instance.get(f"style:{user_id}")

    if not style or style in ["auto", "multi"]:
        style = detect_tone(text)

    if not await redis_instance.get(f"style:{user_id}"):
        await redis_instance.set(f"style:{user_id}", style, ex=604800)

    base_prompt = (
        "คุณคือ 'พี่หลาม' หรือ 'พรี่หลาม' เป็นบอทผู้ช่วยที่พูดจาเป็นกันเองเหมือนมนุษย์ไทย "
        "ใช้ภาษาพูดธรรมดา ไม่เป็นทางการมาก มีอารมณ์ขันบ้างแต่ไม่เกรียน "
        "ตอบคำถามด้วยความจริงใจ เข้าใจง่าย และไม่แสดงตัวว่าเป็น AI เว้นแต่มีคนถามตรง ๆ\n\n"
        "หากมีคำถามเกี่ยวกับตัวคุณ เช่น ใครสร้างพี่หลาม หรือพี่หลามทำงานยังไง "
        "ให้ตอบสั้น ๆ แบบมีบุคลิก ไม่ต้องบอกว่าเป็นโมเดลภาษา\n\n"
    )

    styles = {
        "formal": "พี่หลามยังคุยแบบกันเอง แต่ใช้ภาษาสุภาพขึ้น เคารพคนฟัง เหมาะกับคนที่ชอบความเรียบร้อย ไม่หยาบ ไม่แซะ",
        "troll": "พี่หลามสายกวน มุกมาเต็ม ฮาแบบเนียน ๆ เหมาะกับคนชอบคลายเครียด",
        "neutral": "พี่หลามเป็นวัยรุ่นไทยคนนึง คุยง่าย สบาย ๆ มีมุกบ้าง เข้าใจเร็ว ตรงประเด็น",
    }

    return base_prompt + styles.get(style, styles["neutral"])

@bot.event
async def on_ready():
    await setup_connection()
    await create_table()
    await bot.tree.sync()
    logger.info(f"🚀 {bot.user} is ready!")

async def send_long_reply(message: discord.Message, content: str) -> None:
    chunks = [clean_output_text(content)[i:i + 2000] for i in range(0, len(content), 2000)]
    if chunks:
        await message.reply(chunks[0])
        for chunk in chunks[1:]:
            await message.channel.send(chunk)

async def smart_reply(message: discord.Message, content: str):
    content = clean_output_text(content)
    
    if len(content) > 2000:
        await send_long_reply(message, content)
        return

    try:
        await message.reply(content)
    except discord.HTTPException as e:
        if "Unknown message" in str(e) or e.code == 50035:
            # ถ้า reply ไม่ได้เพราะ message หาย → fallback เป็น send()
            await message.channel.send(content)
        else:
            raise  # ถ้า error อื่นให้ throw ไปเลย

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.channel.id != CHANNEL_ID:
        return

    text = message.content.strip()
    lowered = text.lower()

    topic = match_topic(lowered)
    if topic == "image":
        query = re.sub(r"^(ดูรูป|ค้นรูป|หารูป|ขอรูป)[:,\s]*", "", lowered)
        if not query:
            prev_query = await redis_instance.get(f"last_image_query:{message.author.id}")
            if prev_query:
                query = prev_query
        if query:
            await redis_instance.set(f"last_image_query:{message.author.id}", query, ex=300)
            image_url = await search_image(query, settings)
            image_url = clean_url(image_url)
            return await smart_reply(message, image_url or f"😿 ไม่พบรูปเกี่ยวกับ “{query}”")
        return await smart_reply(message, "📷 พิมพ์ว่า `ดูรูป: แมว` ลองดูสิ")

    elif topic == "lotto":
        return await smart_reply(message, await get_lottery_results())

    elif topic == "exchange":
        return await smart_reply(message, await get_exchange_rate())

    elif topic == "gold":
        return await smart_reply(message, await get_gold_price_today())

    elif topic == "oil":
        return await smart_reply(message, await get_oil_price_today())

    elif topic == "news":
        return await smart_reply(message, await get_daily_news())

    elif topic == "global_news":
        return await smart_reply(message, await get_global_news())

    elif topic == "weather":
        match = re.search(r"(ที่|จังหวัด|เมือง)\s+(.+)", lowered)
        city = match.group(2).strip() if match else None
        if city:
            eng_city = convert_thai_to_english_city(city)
            return await smart_reply(message, await get_weather(eng_city))
        return await smart_reply(message, "📍 พิมพ์ว่า `อากาศที่ เชียงใหม่`")

    elif topic == "tarot":
        return await smart_reply(message, "🔮 อยากดูดวงเรื่องอะไรดี? พิมพ์: ความรัก, การงาน, การเงิน, สุขภาพ")

    elif lowered in ["ความรัก", "การงาน", "การเงิน", "สุขภาพ"]:
        return await smart_reply(message, await draw_cards_and_interpret_by_topic(lowered))

    elif any(kw in lowered for kw in ["วันนี้วันอะไร", "วันอะไรวันนี้"]):
        return await smart_reply(message, f"📅 วันนี้คือ {get_thai_datetime_now()}")

    elif any(kw in lowered for kw in ["กี่โมง", "เวลากี่โมง"]):
        return await smart_reply(message, f"🕒 ขณะนี้คือ {get_thai_datetime_now()}")

    # 👤 Personality
    model = "gpt-4o-mini"
    system_prompt = await process_message(message.author.id, text)

    timezone = await redis_instance.get(f"timezone:{message.author.id}") or "Asia/Bangkok"
    now = datetime.now(pytz.timezone(timezone))
    system_prompt += f"""

⏰ timezone: {timezone}
🕒 {format_thai_datetime(now)}
"""

    messages = await build_chat_context(
        redis_instance,
        message.author.id,
        text,
        system_prompt=system_prompt,
        limit=3
    )

    async with message.channel.typing():
        notify = None

        reply = await get_openai_response(
            messages,
            settings=settings,
            model=model,
            use_web_fallback=True,
            fallback_model="gpt-4o-mini-search-preview"
        )

        if not reply:
            logger.warning("❌ GPT ไม่ตอบอะไรเลย")
            return await smart_reply(message, "⚠️ พี่หลามงงเลย ตอบไม่ได้จริง ๆ จ้า")

        if "🔍 กำลังค้นหาข้อมูลจาก Google..." in reply:
            notify = await message.channel.send("🔍 กำลังค้นหาข้อมูลจาก Google...")

        if notify:
            await notify.delete()

        reply_content = clean_url(clean_output_text(format_response_markdown(reply)))
        await smart_reply(message, reply_content)
        await store_chat(redis_instance, message.author.id, {
            "question": text,
            "response": reply_content
        })

# ✅ Entry point
async def main():
    await setup_connection()
    if bot.pool and redis_instance:
        await bot.start(settings.DISCORD_TOKEN)
    else:
        logger.error("❌ ไม่สามารถเริ่มบอทได้ เพราะเชื่อมต่อ Redis หรือ DB ไม่สำเร็จ")

if __name__ == "__main__":
    asyncio.run(main())
