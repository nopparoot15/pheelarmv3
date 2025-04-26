import re
from typing import Optional

# ✅ ฟังก์ชัน search ที่ใช้ใน GPT tools (สำหรับ function calling)
search_tool = {
    "type": "function",
    "function": {
        "name": "search_google",
        "description": "ค้นหาข้อมูลจาก Google",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "คำค้นหาที่ต้องการค้นจาก Google"
                }
            },
            "required": ["query"]
        }
    }
}

def preserve_blocks(raw: str) -> tuple[str, dict]:
    """เก็บโค้ดบล็อค, ตาราง, หรือ inline code ไว้ก่อน เพื่อไม่ให้โดนแก้ตอน clean"""
    code_blocks = {}

    def replacer(match):
        key = f"__BLOCK_{len(code_blocks)}__"
        code_blocks[key] = match.group(0)
        return key

    raw = re.sub(r"```.*?```", replacer, raw, flags=re.DOTALL)
    raw = re.sub(r"`[^`\n]+`", replacer, raw)
    raw = re.sub(r"^\s*\|.+\|.*$", replacer, raw, flags=re.MULTILINE)

    return raw, code_blocks

def restore_blocks(text: str, blocks: dict) -> str:
    """ใส่โค้ดบล็อคและตารางที่เก็บไว้กลับเข้าที่เดิม"""
    for key, value in blocks.items():
        text = text.replace(key, value)
    return text

def clean_output_text(text: str) -> str:
    """จัดข้อความจาก GPT ให้อ่านง่ายและปลอดภัยจาก markdown error"""
    text, saved_blocks = preserve_blocks(text)

    # ✅ ลบช่องว่างท้ายบรรทัด และลดการขึ้นบรรทัดใหม่เกินจำเป็น
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # ✅ แปลง heading markdown เช่น ### หัวข้อ → **หัวข้อ**
    text = re.sub(r'^#{2,6}\s*(.+)', r'**\1**', text, flags=re.MULTILINE)

    # ✅ bullet: *, -, • → • (ถ้าขึ้นต้นบรรทัด)
    text = re.sub(r'(?m)^[\*\-\u2022]\s+', '• ', text)

    # ✅ ลบ * เดี่ยว ๆ ที่อาจทำ markdown เพี้ยน
    text = re.sub(r'(?<!\*)\*(?!\*)', '', text)

    # ✅ ลบ ** เดี่ยว ๆ ที่ไม่มีคำอยู่ติด เช่น "** ", " **", หรือ "**\n"
    text = re.sub(r'\*\*(\s|$)', r'\1', text)
    text = re.sub(r'(^|\s)\*\*(?=\s)', r'\1', text)

    # ✅ ป้องกัน markdown error จากลิงก์: [text](url) → text <url>
    text = re.sub(r'$begin:math:display$([^$end:math:display$]+)\]$begin:math:text$(https?://[^$end:math:text$]+)\)', r'\1 <\2>', text)
    text = re.sub(r'(?<!<)(https?://\S+)(?!>)', r'<\1>', text)

    # ✅ ถ้าเจอรูปแบบ "ngthai.com <https://ngthai.com/...>" → เอาแค่ <ลิงก์>
    text = re.sub(r'(?m)^(\s*)[^\s<>]+\.(com|org|net|go\.th)\s+<((https?://)[^>\s]+)>', r'\1<\3>', text)

    # ✅ เชื่อมบรรทัดที่ไม่ควรตัด
    safe_starts = r'[\-\*\u2022#>\|0-9]|<:|:.*?:'
    safe_ends = r'[A-Za-z0-9ก-๙\.\!\?\)]'
    text = re.sub(fr'(?<!{safe_ends})\n(?!{safe_starts}|\n)', ' ', text)

    # ✅ แบ่งย่อหน้าให้สมดุล (~40 คำ/ย่อหน้า)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    new_text, current_length = '', 0
    for sentence in sentences:
        sentence_length = len(sentence.split())
        if current_length + sentence_length > 40:
            new_text = new_text.strip() + "\n\n" + sentence.strip() + " "
            current_length = sentence_length
        else:
            new_text += sentence.strip() + " "
            current_length += sentence_length

    text = restore_blocks(new_text, saved_blocks)

    # ✅ เชื่อมเลขลำดับ เช่น "6.\nเนื้อหา" → "6. เนื้อหา"
    text = re.sub(r'(?m)^(\d\.)\s*\n+(\S)', r'\1 \2', text)

    return text.strip()

def clean_url(url: Optional[str]) -> str:
    """ลบ \n \r ออกจาก URL"""
    if not isinstance(url, str):
        return ""
    return re.sub(r'[\n\r]', '', url)

def format_response_markdown(text: str) -> str:
    """จัด markdown เช่น bullet point และลิงก์ ให้ถูกต้อง"""
    lines = text.split("\n")
    formatted_lines = []

    bullet_pattern = re.compile(r'^[•\-\*\u2022]\s*')
    for line in lines:
        line = line.strip()
        if bullet_pattern.match(line):
            content = bullet_pattern.sub('', line).strip()
            formatted_lines.append(f"• {content}")
        else:
            formatted_lines.append(line)

    formatted_text = "\n".join(formatted_lines)
    formatted_text = re.sub(r'<$begin:math:text$(https?://[^\\s]+)$end:math:text$>', r'<\1>', formatted_text)
    formatted_text = re.sub(r'\*\*(.+?)\*\*', r'**\1**', formatted_text)

    return formatted_text.strip()