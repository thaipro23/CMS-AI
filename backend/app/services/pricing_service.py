from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings


PRICING_URL = os.getenv('OPENAI_PRICING_URL', 'https://developers.openai.com/api/docs/pricing')
PRICING_CACHE_PATH = Path(os.getenv('OPENAI_PRICING_CACHE_PATH', '/app/.runtime/openai-pricing-cache.json'))
PRICING_CACHE_TTL_SECONDS = int(os.getenv('OPENAI_PRICING_CACHE_TTL_SECONDS', '21600'))  # 6 hours

# Fallback values are intentionally small and explicit. The live pricing fetch
# reads the official pricing page first; this map is only used when the server is
# offline or the page format changes. Keep gpt-5-mini for this project because
# older project reports used it even if the current pricing page may not list it.
FALLBACK_STANDARD_SHORT_PRICING: dict[str, dict[str, float]] = {
    'gpt-5-mini': {'input': 0.25, 'cached_input': 0.025, 'output': 2.00},
    'gpt-5.4-mini': {'input': 0.75, 'cached_input': 0.075, 'output': 4.50},
    'gpt-5.4-nano': {'input': 0.20, 'cached_input': 0.02, 'output': 1.25},
    'gpt-5.4': {'input': 2.50, 'cached_input': 0.25, 'output': 15.00},
    'gpt-5.5': {'input': 5.00, 'cached_input': 0.50, 'output': 30.00},
}


@dataclass
class ModelPricing:
    model: str
    input_price_per_1m: float
    cached_input_price_per_1m: float
    output_price_per_1m: float
    currency: str = 'USD'
    unit: str = '1M tokens'
    service_tier: str = 'standard'
    context: str = 'short'
    source: str = 'settings_fallback'
    fetched_at: float | None = None
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.fetched_at:
            data['fetched_at_iso'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(self.fetched_at))
        return data


class OpenAIPricingService:
    """Fetch and cache model pricing for cost metering.

    OpenAI exposes pricing publicly as a docs/pricing page. This service provides
    our own backend API for realtime-ish pricing by fetching that page, parsing
    standard short-context token prices, caching them and falling back to admin
    configured prices when a model is missing or the network is unavailable.
    """

    def _settings_pricing(self, model: str, note: str | None = None) -> ModelPricing:
        fallback = FALLBACK_STANDARD_SHORT_PRICING.get(model)
        if fallback:
            return ModelPricing(
                model=model,
                input_price_per_1m=fallback['input'],
                cached_input_price_per_1m=fallback['cached_input'],
                output_price_per_1m=fallback['output'],
                source='static_fallback',
                note=note or 'Không lấy được giá realtime; dùng fallback trong project.',
            )
        return ModelPricing(
            model=model,
            input_price_per_1m=settings.cost_input_price_per_1m,
            cached_input_price_per_1m=settings.cost_cached_input_price_per_1m,
            output_price_per_1m=settings.cost_output_price_per_1m,
            source='settings_fallback',
            note=note or 'Model không có trong giá realtime/fallback; dùng giá admin settings.',
        )

    def _read_cache(self) -> dict[str, Any]:
        if not PRICING_CACHE_PATH.exists():
            return {}
        try:
            data = json.loads(PRICING_CACHE_PATH.read_text(encoding='utf-8'))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _write_cache(self, data: dict[str, Any]) -> None:
        try:
            PRICING_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            PRICING_CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            # Pricing is optional governance metadata. Do not break generation if
            # cache cannot be written in a locked-down container.
            pass

    def _parse_official_pricing_page(self, html: str) -> dict[str, dict[str, float]]:
        # The docs page is rendered as text/HTML and includes compact rows like:
        # gpt-5.4-mini$0.75$0.075$4.50---
        # We only parse rows with input + cached input + output values. Pro rows
        # with '-' cached input are skipped and should use settings/fallback.
        prices: dict[str, dict[str, float]] = {}
        pattern = re.compile(
            r'(?P<model>gpt-[a-zA-Z0-9_.-]+)\$'
            r'(?P<input>[0-9]+(?:\.[0-9]+)?)\$'
            r'(?P<cached>[0-9]+(?:\.[0-9]+)?)\$'
            r'(?P<output>[0-9]+(?:\.[0-9]+)?)'
        )
        for match in pattern.finditer(html):
            model = match.group('model')
            # First occurrence on the pricing page is the Standard/short-context
            # row for flagship models. Later duplicate rows are Batch/Flex/etc.;
            # keep the first one for normal API calls.
            if model in prices:
                continue
            prices[model] = {
                'input': float(match.group('input')),
                'cached_input': float(match.group('cached')),
                'output': float(match.group('output')),
            }
        return prices

    async def refresh_pricing(self) -> dict[str, Any]:
        now = time.time()
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(PRICING_URL, follow_redirects=True)
        if response.status_code >= 400:
            raise RuntimeError(f'OpenAI pricing fetch failed {response.status_code}: {response.text[:500]}')
        parsed = self._parse_official_pricing_page(response.text)
        data = {
            'source_url': str(response.url),
            'fetched_at': now,
            'service_tier': 'standard',
            'context': 'short',
            'prices': parsed,
        }
        self._write_cache(data)
        return data

    async def get_pricing(self, model: str | None = None, *, refresh: bool = False) -> ModelPricing:
        model_name = model or settings.openai_model
        now = time.time()
        cache = self._read_cache()
        is_fresh = bool(cache.get('fetched_at')) and now - float(cache.get('fetched_at', 0)) < PRICING_CACHE_TTL_SECONDS

        if refresh or not is_fresh:
            try:
                cache = await self.refresh_pricing()
            except Exception as exc:
                return self._settings_pricing(model_name, note=f'Không lấy được giá realtime: {exc}')

        prices = cache.get('prices') or {}
        row = prices.get(model_name)
        if row:
            return ModelPricing(
                model=model_name,
                input_price_per_1m=float(row['input']),
                cached_input_price_per_1m=float(row['cached_input']),
                output_price_per_1m=float(row['output']),
                source='openai_pricing_page_live' if refresh else 'openai_pricing_page_cache',
                fetched_at=float(cache.get('fetched_at') or now),
                note='Giá lấy từ trang pricing chính thức của OpenAI, cache theo backend.',
            )
        return self._settings_pricing(model_name, note='Không tìm thấy model trên pricing page hiện tại; dùng giá fallback/settings.')
