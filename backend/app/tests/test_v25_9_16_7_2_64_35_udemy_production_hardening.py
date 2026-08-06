from __future__ import annotations

import os
import sys
import time
from types import SimpleNamespace
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook

from fastapi import HTTPException

from app.core.config import settings
from app.core import operation_rate_limit as operation_limiter
from app.services.academic.udemy_progress import UdemyProgressService


ROOT = Path(__file__).resolve().parents[3]


def _valid_xlsx_bytes() -> bytes:
    raw = BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.append(['Email', 'Tiến độ hiện tại'])
    ws.append(['student@fpt.edu.vn', 50])
    wb.save(raw)
    wb.close()
    return raw.getvalue()


def test_batch35_upload_metadata_and_openxml_validation():
    raw = _valid_xlsx_bytes()
    UdemyProgressService.validate_upload_metadata(
        filename='SOF3032_progress.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    UdemyProgressService._validate_xlsx(raw)

    with pytest.raises(ValueError, match='Content-Type'):
        UdemyProgressService.validate_upload_metadata(
            filename='SOF3032_progress.xlsx',
            content_type='text/html',
        )
    with pytest.raises(ValueError, match='workbook'):
        UdemyProgressService._validate_xlsx(b'<html>not xlsx</html>')


def test_batch35_rejects_unsafe_xlsx_internal_path():
    raw = BytesIO()
    with ZipFile(raw, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        archive.writestr('xl/workbook.xml', '<workbook/>')
        archive.writestr('../escape.txt', 'unsafe')
    with pytest.raises(ValueError, match='đường dẫn nội bộ'):
        UdemyProgressService._validate_xlsx(raw.getvalue())


def test_batch35_rejects_suspicious_xlsx_compression_ratio(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(UdemyProgressService, 'MAX_XLSX_COMPRESSION_RATIO', 10)
    raw = BytesIO()
    with ZipFile(raw, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        archive.writestr('xl/workbook.xml', '<workbook/>')
        archive.writestr('xl/worksheets/sheet1.xml', '0' * (2 * 1024 * 1024))
    with pytest.raises(ValueError, match='tỷ lệ nén bất thường'):
        UdemyProgressService._validate_xlsx(raw.getvalue())


def test_batch35_operation_rate_limit_returns_429(monkeypatch: pytest.MonkeyPatch):
    class FakePipe:
        def incr(self, _key): return self
        def expire(self, _key, _ttl): return self
        def execute(self): return [7, True]

    class FakeRedisClient:
        def pipeline(self): return FakePipe()

    fake_redis = SimpleNamespace(Redis=SimpleNamespace(from_url=lambda *_args, **_kwargs: FakeRedisClient()))
    monkeypatch.setitem(sys.modules, 'redis', fake_redis)
    with pytest.raises(HTTPException) as exc_info:
        operation_limiter.enforce_operation_rate_limit(namespace='test', actor_id='u1', limit=6)
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail['code'] == 'OPERATION_RATE_LIMITED'


def test_batch35_operation_rate_limit_fails_closed_in_hardened_env(monkeypatch: pytest.MonkeyPatch):
    fake_redis = SimpleNamespace(Redis=SimpleNamespace(from_url=lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionError('redis down'))))
    monkeypatch.setitem(sys.modules, 'redis', fake_redis)
    monkeypatch.setattr(operation_limiter, 'is_hardened_deployment', lambda: True)
    with pytest.raises(HTTPException) as exc_info:
        operation_limiter.enforce_operation_rate_limit(namespace='test', actor_id='u1', limit=6)
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail['code'] == 'OPERATION_RATE_LIMIT_UNAVAILABLE'


def test_batch35_retention_cleanup_only_deletes_expired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, 'academic_udemy_file_retention_hours', 1)
    monkeypatch.setattr(settings, 'academic_udemy_export_file_retention_hours', 1)
    old_import = tmp_path / 'udemy-progress-imports' / 'old-job' / 'source.xlsx'
    new_import = tmp_path / 'udemy-progress-imports' / 'new-job' / 'source.xlsx'
    old_export = tmp_path / 'udemy-progress-exports' / 'old.xlsx'
    for path in [old_import, new_import, old_export]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x')
    old_time = time.time() - 7200
    os.utime(old_import, (old_time, old_time))
    os.utime(old_export, (old_time, old_time))

    result = UdemyProgressService.cleanup_expired_artifacts(root=tmp_path)

    assert result['deleted_files'] == 2
    assert not old_import.exists()
    assert not old_export.exists()
    assert new_import.exists()


def test_batch35_retention_cleanup_preserves_active_import_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, 'academic_udemy_file_retention_hours', 1)
    active = tmp_path / 'udemy-progress-imports' / 'active-job' / 'source.xlsx'
    expired = tmp_path / 'udemy-progress-imports' / 'expired-job' / 'source.xlsx'
    for path in [active, expired]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x')
        old_time = time.time() - 7200
        os.utime(path, (old_time, old_time))

    result = UdemyProgressService.cleanup_expired_artifacts(
        root=tmp_path,
        protected_import_job_ids={'active-job'},
    )

    assert result['deleted_files'] == 1
    assert active.exists()
    assert not expired.exists()


def test_batch35_cross_layer_hardening_contract():
    config = (ROOT / 'backend/app/core/config.py').read_text(encoding='utf-8')
    routes = (ROOT / 'backend/app/api/routes/academic.py').read_text(encoding='utf-8')
    worker = (ROOT / 'backend/app/worker.py').read_text(encoding='utf-8')
    service = (ROOT / 'backend/app/services/academic/udemy_progress.py').read_text(encoding='utf-8')
    compose = (ROOT / 'docker-compose.prod.yml').read_text(encoding='utf-8')
    frontend = (ROOT / 'frontend/app/subject-management/[deliveryId]/udemy/page.tsx').read_text(encoding='utf-8')
    migration = (ROOT / 'backend/alembic/versions/0057_v25_9_16_7_2_64_35_udemy_hardening_indexes.py').read_text(encoding='utf-8')

    assert "app_version: str = '25.9.16.7.2.64.16.5.7.2.5'" in config
    assert 'academic_udemy_upload_rate_limit_per_minute' in config
    assert 'MAX_XLSX_COMPRESSION_RATIO' in service
    assert 'cleanup_expired_artifacts' in service
    assert "@router.post('/subject-deliveries/{delivery_id}/udemy-progress/export-jobs'" in routes
    assert "@router.get('/udemy/progress/export-jobs/{job_id}/download')" in routes
    assert "name='academic_udemy_progress_export_task'" in worker
    assert "name='academic_udemy_artifact_cleanup_task'" in worker
    assert "'academic_udemy_progress_export_task': {'queue': 'exports'}" in worker
    assert 'createUdemyProgressExportJob' in frontend
    assert 'getAcademicBulkOperationJob' in frontend
    assert '--hostname=worker-heavy@%h' in compose
    assert 'worker-heavy@$$(hostname)' in compose
    assert "down_revision = '0056_v25_9_16_7_2_64_33'" in migration
    assert 'legacy ACMS data' in migration


def test_batch35_has_no_acms_transfer_implementation():
    migration = (ROOT / 'backend/alembic/versions/0057_v25_9_16_7_2_64_35_udemy_hardening_indexes.py').read_text(encoding='utf-8').lower()
    routes = (ROOT / 'backend/app/api/routes/academic.py').read_text(encoding='utf-8').lower()
    worker = (ROOT / 'backend/app/worker.py').read_text(encoding='utf-8').lower()
    forbidden = ['grade_report_udemy', 'deadline_week1', 'percent_week1', 'subject.is_udemy']
    assert all(item not in migration for item in forbidden)
    assert all(item not in routes for item in forbidden)
    assert all(item not in worker for item in forbidden)
