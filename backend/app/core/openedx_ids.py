from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

_COURSE_KEY_RE = re.compile(
    r"course-v1:([^+/\s?#]+)\+([^+/\s?#]+)\+([^+/\s?#]+)",
    re.IGNORECASE,
)


def normalize_openedx_course_id(value: object, *, required: bool = False) -> str:
    """Return one canonical Open edX course key.

    Accepts the canonical key, a URL-encoded key, or a Studio/LMS URL containing
    a key. Path suffixes and the common accidental trailing slash are removed.
    The function intentionally does not rewrite org/course/run casing.
    """
    raw = unquote(str(value or "")).strip()
    if not raw:
        if required:
            raise ValueError("Thiếu Open edX Course ID.")
        return ""

    # URL inputs are common when operators copy the current Studio address.
    parsed = urlparse(raw)
    candidate = unquote(parsed.path) if parsed.scheme and parsed.netloc else raw
    match = _COURSE_KEY_RE.search(candidate)
    if not match:
        match = _COURSE_KEY_RE.search(raw)
    if not match:
        if required:
            raise ValueError("Course ID phải có dạng course-v1:ORG+COURSE+RUN.")
        return ""
    return f"course-v1:{match.group(1)}+{match.group(2)}+{match.group(3)}"


def openedx_course_id_candidates(value: object) -> tuple[str, ...]:
    """Canonical and legacy forms used to read rows created by older builds."""
    canonical = normalize_openedx_course_id(value)
    if not canonical:
        return ()
    return canonical, f"{canonical}/"
