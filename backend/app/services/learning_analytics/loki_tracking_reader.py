from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx


@dataclass(slots=True)
class LokiTrackingEntry:
    timestamp_ns: int
    line: str
    pod: str | None = None
    app: str | None = None


@dataclass(slots=True)
class LokiTrackingReadResult:
    entries: list[LokiTrackingEntry]
    start_cursor_ns: int
    end_cursor_ns: int
    safe_end_ns: int
    pages: int
    windows: int
    caught_up: bool
    base_url: str
    query: str


class LokiTrackingLogReader:
    """Bounded forward reader for Open edX tracking events stored in Loki.

    The cursor is a Loki nanosecond timestamp. A run walks small time windows
    and stops when it catches up to the safety lag or reaches the configured
    line/page cap. The caller persists the returned cursor only after database
    writes are committed.
    """

    def __init__(
        self,
        *,
        base_url: str,
        query: str,
        window_seconds: int = 600,
        lag_seconds: int = 120,
        limit: int = 1000,
        timeout_seconds: float = 60.0,
        page_sleep_seconds: float = 0.3,
        max_pages: int = 100,
        max_lines: int = 50000,
        tenant_id: str | None = None,
    ):
        self.base_url = str(base_url or '').strip().rstrip('/')
        self.query = str(query or '').strip()
        self.window_ns = max(1, int(window_seconds or 600)) * 1_000_000_000
        self.lag_ns = max(0, int(lag_seconds or 120)) * 1_000_000_000
        self.limit = max(1, min(int(limit or 1000), 5000))
        self.timeout_seconds = max(1.0, float(timeout_seconds or 60.0))
        self.page_sleep_seconds = max(0.0, float(page_sleep_seconds or 0.0))
        self.max_pages = max(1, int(max_pages or 100))
        self.max_lines = max(1, int(max_lines or 50000))
        self.tenant_id = str(tenant_id or '').strip() or None
        if not self.base_url:
            raise ValueError('ANALYTICS_LOKI_BASE_URL is required')
        if not self.query:
            raise ValueError('ANALYTICS_LOKI_QUERY is required')

    @staticmethod
    def _iso_to_ns(value: str) -> int:
        text = str(value or '').strip()
        if not text:
            raise ValueError('empty backfill timestamp')
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1_000_000_000)

    def initial_cursor_ns(self, *, backfill_start: str | None = None, default_backfill_hours: int = 24) -> int:
        if str(backfill_start or '').strip():
            return self._iso_to_ns(str(backfill_start))
        safe_end = max(0, time.time_ns() - self.lag_ns)
        return max(0, safe_end - max(1, int(default_backfill_hours or 24)) * 3600 * 1_000_000_000)

    @staticmethod
    def _flatten(payload: dict) -> list[LokiTrackingEntry]:
        data = payload.get('data') if isinstance(payload, dict) else None
        results = data.get('result') if isinstance(data, dict) else None
        if not isinstance(results, list):
            return []
        rows: list[LokiTrackingEntry] = []
        for result in results:
            if not isinstance(result, dict):
                continue
            stream = result.get('stream') if isinstance(result.get('stream'), dict) else {}
            values = result.get('values') if isinstance(result.get('values'), list) else []
            pod = str(stream.get('pod') or '').strip() or None
            app = str(stream.get('app') or '').strip() or None
            for value in values:
                if not isinstance(value, (list, tuple)) or len(value) < 2:
                    continue
                try:
                    timestamp_ns = int(value[0])
                except (TypeError, ValueError):
                    continue
                rows.append(
                    LokiTrackingEntry(
                        timestamp_ns=timestamp_ns,
                        line=str(value[1] or ''),
                        pod=pod,
                        app=app,
                    )
                )
        rows.sort(key=lambda item: item.timestamp_ns)
        return rows

    def read_from(self, *, cursor_ns: int) -> LokiTrackingReadResult:
        cursor = max(0, int(cursor_ns or 0))
        start_cursor = cursor
        safe_end = max(0, time.time_ns() - self.lag_ns)
        entries: list[LokiTrackingEntry] = []
        pages = 0
        windows = 0
        headers = {'X-Scope-OrgID': self.tenant_id} if self.tenant_id else None

        with httpx.Client(timeout=self.timeout_seconds, headers=headers) as client:
            while cursor < safe_end and pages < self.max_pages and len(entries) < self.max_lines:
                window_end = min(cursor + self.window_ns, safe_end)
                page_start = cursor
                window_complete = False
                windows += 1

                while pages < self.max_pages and len(entries) < self.max_lines:
                    request_limit = min(self.limit, self.max_lines - len(entries))
                    response = client.get(
                        f'{self.base_url}/loki/api/v1/query_range',
                        params={
                            'query': self.query,
                            'start': str(page_start),
                            'end': str(window_end),
                            'limit': str(request_limit),
                            'direction': 'forward',
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict) or payload.get('status') != 'success':
                        raise RuntimeError('Loki query_range returned a non-success payload')

                    rows = self._flatten(payload)
                    pages += 1
                    entries.extend(rows)

                    if len(rows) < request_limit:
                        window_complete = True
                        break

                    last_ts = rows[-1].timestamp_ns
                    next_start = last_ts if last_ts > page_start else last_ts + 1
                    page_start = max(page_start + 1, next_start)
                    if self.page_sleep_seconds:
                        time.sleep(self.page_sleep_seconds)

                if window_complete:
                    cursor = window_end + 1
                else:
                    cursor = page_start
                    break

                if self.page_sleep_seconds and cursor < safe_end:
                    time.sleep(self.page_sleep_seconds)

        return LokiTrackingReadResult(
            entries=entries,
            start_cursor_ns=start_cursor,
            end_cursor_ns=cursor,
            safe_end_ns=safe_end,
            pages=pages,
            windows=windows,
            caught_up=cursor >= safe_end,
            base_url=self.base_url,
            query=self.query,
        )
