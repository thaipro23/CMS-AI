"""Dedicated backend-to-backend credentials; independent of Dash user sessions."""
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Header, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.core.config import settings

key_header = APIKeyHeader(name='X-AP-API-Key', scheme_name='APAPIKey', auto_error=False)


class ClientScope(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    branch: Literal['poly', 'ptcd']
    campuses: tuple[Annotated[str, Field(min_length=1, max_length=64)], ...] = Field(min_length=1)


class ClientConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    key_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    scopes: tuple[ClientScope, ...] = Field(min_length=1)


@dataclass(frozen=True)
class APAnalyticsClient:
    client_id: str
    scopes: tuple[ClientScope, ...]

    def assert_scope(self, branch: str, campus: str) -> None:
        if not any(s.branch == branch and campus in s.campuses for s in self.scopes):
            raise HTTPException(status_code=403, detail='AP_SCOPE_FORBIDDEN')


def get_ap_analytics_client(
    client_id: str | None = Header(default=None, alias='X-AP-Client-Id', description='Required integration client ID; missing or invalid credentials return 401.'),
    api_key: str | None = Security(key_header),
) -> APAnalyticsClient:
    try:
        raw = json.loads(settings.ap_analytics_clients_json.get_secret_value() or '{}')
        if not isinstance(raw, dict) or not raw:
            raise ValueError('Empty configuration')
        configs = TypeAdapter(dict[Annotated[str, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')], ClientConfig]).validate_python(raw)
    except (ValueError, TypeError, ValidationError):
        raise HTTPException(status_code=503, detail='AP_INTEGRATION_NOT_CONFIGURED') from None
    config = configs.get(client_id or '')
    digest = hashlib.sha256((api_key or '').encode()).hexdigest()
    valid = hmac.compare_digest(digest, config.key_sha256 if config else '0' * 64)
    if not client_id or not config or not api_key or not valid:
        raise HTTPException(status_code=401, detail='INVALID_AP_CREDENTIALS')
    return APAnalyticsClient(client_id=client_id, scopes=config.scopes)
