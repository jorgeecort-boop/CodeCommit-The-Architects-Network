import html
import re


SCRIPT_TAG_RE = re.compile(r"<\s*/?\s*script[^>]*>", re.IGNORECASE)
SQL_META_RE = re.compile(r"(--|;|/\*|\*/|\b(OR|AND)\b\s+\d=\d)", re.IGNORECASE)
SQL_DDL_RE = re.compile(r"\b(DROP\s+TABLE|TRUNCATE\s+TABLE|DELETE\s+FROM)\b", re.IGNORECASE)


def sanitize_chat_message(raw: str, max_len: int = 1000) -> str:
    text = raw.strip()[:max_len]
    text = SCRIPT_TAG_RE.sub("", text)
    text = SQL_META_RE.sub("", text)
    text = SQL_DDL_RE.sub("", text)
    return html.escape(text, quote=True)
