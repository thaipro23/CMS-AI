from __future__ import annotations

import io
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.object_storage import ObjectStorage, StorageError


class _Response(io.BytesIO):
    def release_conn(self):
        return None


class FakeMinio:
    def __init__(self):
        self.buckets = {'ai-server'}
        self.objects: dict[tuple[str, str], bytes] = {}

    def bucket_exists(self, bucket):
        return bucket in self.buckets

    def make_bucket(self, bucket, region=None):
        del region
        self.buckets.add(bucket)

    def put_object(self, bucket, key, data, length, content_type=None):
        del content_type
        self.objects[(bucket, key)] = data.read(length)

    def get_object(self, bucket, key):
        return _Response(self.objects[(bucket, key)])

    def stat_object(self, bucket, key):
        if (bucket, key) not in self.objects:
            exc = RuntimeError('missing')
            exc.code = 'NoSuchKey'
            raise exc
        return SimpleNamespace(
            size=len(self.objects[(bucket, key)]),
            last_modified=datetime.now(timezone.utc),
        )

    def remove_object(self, bucket, key):
        self.objects.pop((bucket, key), None)

    def list_objects(self, bucket, prefix='', recursive=True):
        del recursive
        for (item_bucket, key), raw in sorted(self.objects.items()):
            if item_bucket == bucket and key.startswith(prefix):
                yield SimpleNamespace(
                    object_name=key,
                    size=len(raw),
                    last_modified=datetime.now(timezone.utc),
                )


def _config(tmp_path, *, provider='local', endpoint='https://s3.fpl.edu.vn'):
    return SimpleNamespace(
        storage_provider=provider,
        local_storage_path=str(tmp_path),
        minio_endpoint=endpoint,
        minio_access_key='ai-access',
        minio_secret_key='ai-secret',
        minio_bucket='ai-server',
        minio_secure=True,
        minio_region=None,
        minio_cert_check=True,
        minio_auto_create_bucket=False,
    )


def test_local_storage_round_trip_and_traversal_guard(tmp_path):
    storage = ObjectStorage(_config(tmp_path))
    reference = storage.put_bytes('question-bank/v1/file.txt', b'hello')

    assert storage.read_bytes(reference) == b'hello'
    assert storage.stat(reference).size == 5
    assert storage.delete(reference) is True
    assert storage.exists(reference) is False
    with pytest.raises(StorageError, match='key'):
        storage.put_bytes('../escape.txt', b'x')
    with pytest.raises(StorageError, match='key'):
        storage.put_bytes('/absolute.txt', b'x')


def test_minio_https_round_trip_private_uri_and_legacy_local_read(tmp_path):
    fake = FakeMinio()
    storage = ObjectStorage(_config(tmp_path, provider='minio'), minio_client=fake)

    reference = storage.put_bytes('question-bank/v1/tài liệu.pdf', b'pdf', content_type='application/pdf')

    assert reference == 'minio://ai-server/question-bank/v1/t%C3%A0i%20li%E1%BB%87u.pdf'
    assert storage.read_bytes(reference) == b'pdf'
    assert [item.key for item in storage.list_objects('question-bank')] == ['question-bank/v1/tài liệu.pdf']
    assert storage.endpoint_summary() == {
        'provider': 'minio',
        'endpoint': 's3.fpl.edu.vn',
        'secure': True,
        'bucket': 'ai-server',
    }

    rollback_config = _config(tmp_path, provider='local')
    rollback_reader = ObjectStorage(rollback_config, minio_client=fake)
    assert rollback_reader.read_bytes(reference) == b'pdf'
    with pytest.raises(StorageError, match='query'):
        storage.read_bytes(f'{reference}?versionId=unexpected')

    legacy = tmp_path / 'question-bank' / 'legacy.txt'
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b'legacy')
    assert storage.read_bytes(str(legacy)) == b'legacy'


def test_minio_bucket_must_be_precreated_in_production(tmp_path):
    fake = FakeMinio()
    fake.buckets.clear()
    storage = ObjectStorage(_config(tmp_path, provider='minio'), minio_client=fake)

    with pytest.raises(StorageError, match='không tồn tại'):
        storage.put_bytes('reports/a.xlsx', b'x')


def test_minio_health_write_read_delete_smoke(tmp_path):
    fake = FakeMinio()
    storage = ObjectStorage(_config(tmp_path, provider='minio'), minio_client=fake)

    result = storage.health(write_test=True)

    assert result['status'] == 'ok'
    assert result['write_test'] is True
    assert not fake.objects
