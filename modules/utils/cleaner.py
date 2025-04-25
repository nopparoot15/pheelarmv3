import re

# ✅ ฟังก์ชัน search ที่ใช้ใน GPT tools (ใช้ร่วมกับ OpenAI function calling)
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
    for key, value in blocks.items():
        text = text.replace(key, value)
    return text

def clean_output_text(text: str) -> str:
    text, saved_blocks = preserve_blocks(text)

    # ลบช่องว่างท้ายบรรทัดและลดการขึ้นบรรทัดใหม่มากเกินไป
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    safe_starts = r'[\-\*\u2022#>\|0-9]|<:|:.*?:'
    safe_ends = r'[A-Za-z0-9ก-๙\.\!\?\)]'

    text = re.sub(
        fr'(?<!{safe_ends})\n(?!{safe_starts}|\n)',
        ' ',
        text
    )

    # เพิ่มการเว้นวรรคย่อหน้าให้ดูอ่านง่ายขึ้น
    sentences = re.split(r'(?<=[.!?])\s+', text)
    new_text, current_length = '', 0

    for sentence in sentences:
        sentence_length = len(sentence.split())
        if current_length + sentence_length > 40:  # ประมาณ 40 คำต่อย่อหน้า
            new_text = new_text.strip() + "\n\n" + sentence.strip() + " "
            current_length = sentence_length
        else:
            new_text += sentence.strip() + " "
            current_length += sentence_length

    text = restore_blocks(new_text, saved_blocks)
    return text.strip()

def clean_url(url: Optional[str]) -> str:
    if not isinstance(url, str):
        return ""
    return re.sub(r'[\n\r]', '', url)
    
def format_response_markdown(text: str) -> str:
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
    formatted_text = re.sub(r'<\((https?://[^\s]+)\)>', r'<\1>', formatted_text)
    formatted_text = re.sub(r'\*\*(.+?)\*\*', r'**\1**', formatted_text)

    return formatted_text.strip()
