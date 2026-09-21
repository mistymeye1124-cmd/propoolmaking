import re
import asyncio
from typing import List
from deep_translator import MyMemoryTranslator

def detect_is_bengali(text: str) -> bool:
    """Returns True if text contains Bengali characters."""
    return bool(re.search(r"[\u0980-\u09FF]", text))

def translate_sync(text: str, source_code: str, target_code: str) -> str:
    try:
        return MyMemoryTranslator(source=source_code, target=target_code).translate(text)
    except Exception:
        return text

async def translate_text_preserving_tags(text: str, target_lang: str) -> str:
    """
    Translates text to target_lang ('en' or 'bn') while preserving HTML tags,
    Telegram Premium Emojis (<tg-emoji ...>), and template variables like {title}.
    """
    if not text or not text.strip():
        return text

    source_is_bn = detect_is_bengali(text)
    if target_lang == "en" and not source_is_bn:
        return text
    if target_lang == "bn" and source_is_bn:
        return text

    source_code = "bn-IN" if source_is_bn else "en-GB"
    target_code = "en-GB" if target_lang == "en" else "bn-IN"

    # Pattern to match HTML tags, Premium Emojis and template variables {var}
    pattern = r"(<tg-emoji[^>]*>.*?</tg-emoji>|<[^>]+>|\{[a-zA-Z0-9_]+\})"
    placeholders: List[str] = []

    def replacer(match):
        idx = len(placeholders)
        placeholders.append(match.group(0))
        return f" [[T{idx}]] "

    protected = re.sub(pattern, replacer, text)

    lines = protected.split("\n")
    translated_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            translated_lines.append("")
            continue
        # Skip lines that are only symbols/delimiters like ━━━━━━━━━━━━━━━━━━━━
        if not re.search(r"[\w\u0980-\u09FF]", stripped):
            translated_lines.append(line)
            continue

        # Run translation in thread pool to avoid blocking asyncio loop
        t_line = await asyncio.to_thread(translate_sync, stripped, source_code, target_code)
        translated_lines.append(t_line or line)

    result = "\n".join(translated_lines)

    # Restore placeholders
    for idx, orig in enumerate(placeholders):
        result = re.sub(rf"\s*\[\[T{idx}\]\]\s*", f" {orig} ", result, flags=re.IGNORECASE)

    # Clean up double spaces around tags
    result = re.sub(r" +", " ", result)
    return result.strip()
