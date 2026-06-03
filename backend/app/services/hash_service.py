import hashlib
import re


def normalize_content(content: str) -> str:
    content = re.sub(r'\s+', ' ', content or '').strip()
    return content.lower()


def content_hash(content: str) -> str:
    normalized = normalize_content(content)
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
