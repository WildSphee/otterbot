import html
import re
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes

# Simple Markdown -> Telegram HTML converter for our bot
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_ITAL = re.compile(r"__(.+?)__|_(.+?)_")
_MD_CODE_INLINE = re.compile(r"`([^`]+)`")
_MD_FENCE = re.compile(r"^```(?:\w+)?\s*([\s\S]*?)\s*```$", re.DOTALL)

def md_to_html(text: str) -> str:
    if not text:
        return ""

    # If it's a fenced block, unwrap (Telegram often shows it raw)
    m = _MD_FENCE.match(text.strip())
    if m:
        text = m.group(1)

    # Strip surrounding single backticks if the whole message is wrapped
    if text.startswith("`") and text.endswith("`"):
        text = text[1:-1]

    # Escape everything first, then re-inject tags we control
    text = html.escape(text)

    # Links: [text](url) -> <a href="url">text</a>
    text = _MD_LINK.sub(lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>', text)

    # Bold **text**
    text = _MD_BOLD.sub(r"<b>\1</b>", text)

    # Italic _text_ or __text__
    def ital_repl(m):
        return f"<i>{m.group(1) or m.group(2)}</i>"
    text = _MD_ITAL.sub(ital_repl, text)

    # Inline code `code`
    text = _MD_CODE_INLINE.sub(r"<code>\1</code>", text)

    # Replace double newlines with <br><br> for nicer spacing
    text = text.replace("\r\n", "\n").replace("\n\n", "<br><br>")

    return text.strip()

def _chunk_telegram(text: str, limit: int = 4096):
    # Telegram text limit per message; split on line breaks
    if len(text) <= limit:
        return [text]
    parts, buf = [], []
    size = 0
    for line in text.split("<br>"):
        add = (line + "<br>")
        if size + len(add) > limit:
            parts.append("".join(buf).rstrip("<br>"))
            buf, size = [add], len(add)
        else:
            buf.append(add)
            size += len(add)
    if buf:
        parts.append("".join(buf).rstrip("<br>"))
    return parts

async def schola_reply(
    update: Update,
    message: str,
    reply_markup: Optional[object] = None,
    parse_mode: str = "HTML",
    *args,
    **kwargs,
) -> None:
    """Send a Telegram reply with graceful Markdown handling and chunking."""
    try:
        html_text = md_to_html(message)
        for chunk in _chunk_telegram(html_text):
            await update.message.reply_text(
                chunk,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                *args,
                **kwargs,
            )
    except Exception as e:
        await update.message.reply_text(f"Exception occurred: {e}\n:(")
