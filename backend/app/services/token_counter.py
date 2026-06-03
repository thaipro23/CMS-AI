"""Token counting helpers.

Production estimates should prefer OpenAI's /v1/responses/input_tokens endpoint.
This local counter is only a fallback for mock mode, chunk display counts,
schema-overhead estimates, output fallback, and offline development.

Important: tiktoken may try to download the cl100k_base encoding from
openaipublic.blob.core.windows.net the first time it is used. In offline Docker
or restricted DNS environments that can raise a network error. Token counting
must never fail a generation job, so this module falls back to a conservative
heuristic when tiktoken cannot load an encoding.
"""

from __future__ import annotations

import logging
import math
import os
import re
from functools import lru_cache

try:
    import tiktoken
except Exception:  # pragma: no cover - optional offline fallback
    tiktoken = None

logger = logging.getLogger(__name__)

# Keep tiktoken cache inside the app volume when it is available. This does not
# force a download, but if the encoding is downloaded once it is shared by the
# backend/worker containers when ./backend is mounted to /app.
os.environ.setdefault('TIKTOKEN_CACHE_DIR', '/app/.runtime/tiktoken-cache')

_WORD_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_WARNED_TIKTOKEN_FAILURES: set[str] = set()


@lru_cache(maxsize=16)
def _load_encoding(model: str):
    if tiktoken is None:
        key = 'module_not_installed'
        if key not in _WARNED_TIKTOKEN_FAILURES:
            _WARNED_TIKTOKEN_FAILURES.add(key)
            logger.warning('tiktoken package unavailable; using heuristic token counter. model=%s', model)
        return None
    try:
        return tiktoken.encoding_for_model(model)
    except Exception as exc_model:
        try:
            return tiktoken.get_encoding('cl100k_base')
        except Exception as exc_base:
            key = f'{type(exc_model).__name__}:{type(exc_base).__name__}'
            if key not in _WARNED_TIKTOKEN_FAILURES:
                _WARNED_TIKTOKEN_FAILURES.add(key)
                logger.warning(
                    'tiktoken encoding unavailable; using heuristic token counter. '
                    'model=%s model_error=%r base_error=%r',
                    model,
                    exc_model,
                    exc_base,
                )
            return None


def heuristic_count_tokens(text: str) -> int:
    """Conservative offline token estimate.

    This is intentionally a little high for Vietnamese/English mixed course
    content so budget hard-stop remains safe when OpenAI token counting is not
    available.
    """
    if not text:
        return 0
    normalized = str(text)
    char_count = len(normalized)
    pieces = len(_WORD_RE.findall(normalized))

    # English often averages ~4 chars/token; Vietnamese with spaces and JSON
    # punctuation can be closer to word/punctuation count. Use the larger value
    # and add a small margin.
    by_chars = math.ceil(char_count / 3.2)
    by_pieces = math.ceil(pieces * 1.35)
    return max(1, by_chars, by_pieces)


def count_tokens(text: str, model: str = 'gpt-5-mini') -> int:
    if not text:
        return 0
    encoding = _load_encoding(model)
    if encoding is None:
        return heuristic_count_tokens(text)
    try:
        return len(encoding.encode(str(text)))
    except Exception as exc:
        logger.warning('tiktoken encode failed; using heuristic token counter. model=%s error=%r', model, exc)
        return heuristic_count_tokens(text)
