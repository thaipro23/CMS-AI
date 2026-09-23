from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


SCHEDULED_SCOPE_POLICY_VERSION = 'academic-scheduled-scope/v1'
SCHEDULED_AUTO_MAP_KEY_PREFIX = 'ap-auto-map:v1:'


class ScheduledScopeError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _clean_required(value: Any, *, field: str) -> str:
    clean = str(value or '').strip()
    if not clean:
        raise ScheduledScopeError(
            f'scope_missing_{field}',
            f'Scheduled scope requires {field}.',
        )
    return clean


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(',', ':'),
        sort_keys=True,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def freeze_scheduled_scope(
    *,
    term_id: str,
    branch: str,
    run_date_vn: str,
    class_to_campus: Mapping[str, Any],
    requested_maximum: Mapping[str, Any],
    policy_version: str = SCHEDULED_SCOPE_POLICY_VERSION,
) -> dict[str, Any]:
    """Build the immutable, canonical scope shared by scheduled descendants."""
    clean_mapping: dict[str, str] = {}
    for raw_class_id, raw_campus in class_to_campus.items():
        class_id = str(raw_class_id or '').strip()
        if not class_id:
            raise ScheduledScopeError(
                'scope_missing_class_id',
                'Scheduled scope contains an empty class ID.',
            )
        campus = str(raw_campus or '').strip().lower()
        if not campus:
            raise ScheduledScopeError(
                'scope_missing_campus',
                f'Scheduled scope class {class_id} has no campus.',
            )
        if campus == 'ho':
            raise ScheduledScopeError(
                'scope_reserved_campus',
                f'Scheduled scope class {class_id} uses reserved campus HO.',
            )
        clean_mapping[class_id] = campus

    ordered_mapping = {
        class_id: clean_mapping[class_id]
        for class_id in sorted(clean_mapping)
    }
    payload = {
        'policy_version': _clean_required(policy_version, field='policy_version'),
        'term_id': _clean_required(term_id, field='term_id'),
        'branch': _clean_required(branch, field='branch').lower(),
        'run_date_vn': _clean_required(run_date_vn, field='run_date_vn'),
        'class_ids': list(ordered_mapping),
        'class_to_campus': ordered_mapping,
        'campuses': sorted(set(ordered_mapping.values())),
        'requested_maximum': {
            str(key): requested_maximum[key]
            for key in sorted(requested_maximum)
        },
    }
    return {
        **payload,
        'scope_hash': _canonical_hash(payload),
    }


def scheduled_auto_map_contract(
    *,
    scheduled_parent_job_id: str,
    ap_sync_run_id: str,
    frozen_scope: Mapping[str, Any],
) -> dict[str, str]:
    return {
        'scheduled_parent_job_id': _clean_required(
            scheduled_parent_job_id,
            field='parent_job_id',
        ),
        'ap_sync_run_id': _clean_required(ap_sync_run_id, field='ap_sync_run_id'),
        'term_id': _clean_required(frozen_scope.get('term_id'), field='term_id'),
        'branch': _clean_required(frozen_scope.get('branch'), field='branch').lower(),
        'run_date_vn': _clean_required(
            frozen_scope.get('run_date_vn'),
            field='run_date_vn',
        ),
        'scope_hash': _clean_required(
            frozen_scope.get('scope_hash'),
            field='scope_hash',
        ),
        'policy_version': _clean_required(
            frozen_scope.get('policy_version'),
            field='policy_version',
        ),
    }


def scheduled_auto_map_key(contract: Mapping[str, Any]) -> str:
    return f'{SCHEDULED_AUTO_MAP_KEY_PREFIX}{_canonical_hash(contract)}'
