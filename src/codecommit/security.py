# security.py – Compatibilidad hacia atrás.
# La lógica real está en content_mod.py.
from .content_mod import sanitize_chat_message, sanitize_post_content, is_content_clean  # noqa: F401
