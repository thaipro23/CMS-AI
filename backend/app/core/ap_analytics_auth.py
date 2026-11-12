"""Dedicated backend-to-backend credentials; independent of Dash user sessions."""
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import HTTPException, Security
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
    scopes: tuple[ClientScope, ...]

    def assert_scope(self, branch: str, campus: str) -> None:
        if not any(s.branch == branch and campus in s.campuses for s in self.scopes):
            raise HTTPException(status_code=403, detail='AP_SCOPE_FORBIDDEN')


def get_ap_analytics_client(
    api_key: str | None = Security(key_header),
) -> APAnalyticsClient:
    try:
        shared = settings.ap_analytics_config_json.get_secret_value()
        if shared:
            config = ClientConfig.model_validate_json(shared)
        else:
            # Accept the previous deployment format only when it contains one key.
            # Never union scopes from multiple clients or let a header select keys.
            raw = json.loads(settings.ap_analytics_clients_json.get_secret_value() or '{}')
            configs = TypeAdapter(dict[Annotated[str, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')], ClientConfig]).validate_python(raw)
            if len(configs) != 1:
                raise ValueError('A single shared key must be configured')
            config = next(iter(configs.values()))
    except (ValueError, TypeError, ValidationError):
        raise HTTPException(status_code=503, detail='AP_INTEGRATION_NOT_CONFIGURED') from None
    digest = hashlib.sha256((api_key or '').encode()).hexdigest()
    if not api_key or not hmac.compare_digest(digest, config.key_sha256):
        raise HTTPException(status_code=401, detail='INVALID_AP_CREDENTIALS')
    return APAnalyticsClient(scopes=config.scopes)
