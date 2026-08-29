from __future__ import annotations

import io
import json
import mimetypes
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator
from urllib.parse import quote, unquote, urlsplit

from app.core.config import settings


MINIO_URI_SCHEME = 'minio'
SUPPORTED_PROVIDERS = {'local', 'minio'}


class StorageError(RuntimeError):
    """Safe storage failure that never contains access credentials."""


@dataclass(frozen=True)
class StoredObject:
    reference: str
    key: str
    size: int
    last_modified: datetime | None = None


def _normalized_key(value: str) -> str:
    raw = str(value or '').replace('\\', '/').strip()
    path = PurePosixPath(raw)
    if not raw or raw.startswith('/') or raw in {'.', '..'} or path.is_absolute() or '..' in path.parts:
        raise StorageError('Object key không hợp lệ.')
    if any(not part or part in {'.', '..'} for part in path.parts):
        raise StorageError('Object key không hợp lệ.')
    if any(ord(char) < 32 for char in raw):
        raise StorageError('Object key chứa ký tự điều khiển không hợp lệ.')
    return path.as_posix()


def _minio_uri(bucket: str, key: str) -> str:
    safe_bucket = str(bucket or '').strip()
    if not safe_bucket or '/' in safe_bucket:
        raise StorageError('Tên bucket MinIO không hợp lệ.')
    return f'{MINIO_URI_SCHEME}://{safe_bucket}/{quote(_normalized_key(key), safe="/-_.~")}'


def _parse_minio_uri(reference: str) -> tuple[str, str] | None:
    parts = urlsplit(str(reference or '').strip())
    if parts.scheme.lower() != MINIO_URI_SCHEME:
        return None
    if parts.query or parts.fragment:
        raise StorageError('Storage URI MinIO không được chứa query hoặc fragment.')
    bucket = parts.netloc.strip()
    key = _normalized_key(unquote(parts.path.lstrip('/')))
    if not bucket:
        raise StorageError('Storage URI thiếu bucket MinIO.')
    return bucket, key


class ObjectStorage:
    """Local/MinIO storage adapter with URI-based backward compatibility.

    New writes follow ``STORAGE_PROVIDER``. Reads and deletes are routed by the
    stored reference, so legacy absolute paths remain usable after switching new
    writes to MinIO and MinIO objects remain readable during a local rollback.
    """

    def __init__(self, config: Any = settings, *, minio_client: Any | None = None):
        self.config = config
        self.provider = str(getattr(config, 'storage_provider', 'local') or 'local').strip().lower()
        if self.provider not in SUPPORTED_PROVIDERS:
            raise StorageError(f'STORAGE_PROVIDER={self.provider!r} chưa được hỗ trợ bởi bản này.')
        self.local_root = Path(getattr(config, 'local_storage_path', '/app/.runtime') or '/app/.runtime').expanduser().resolve()
        self.bucket = str(getattr(config, 'minio_bucket', '') or '').strip()
        self._client_override = minio_client
        self._client_cache: Any | None = None
        self._verified_buckets: set[str] = set()

    def _endpoint(self) -> tuple[str, bool]:
        raw = str(getattr(self.config, 'minio_endpoint', '') or '').strip()
        if not raw:
            raise StorageError('MINIO_ENDPOINT chưa được cấu hình.')
        configured_secure = bool(getattr(self.config, 'minio_secure', False))
        candidate = raw if '://' in raw else f'{"https" if configured_secure else "http"}://{raw}'
        parts = urlsplit(candidate)
        if parts.scheme not in {'http', 'https'} or not parts.netloc:
            raise StorageError('MINIO_ENDPOINT không hợp lệ.')
        if parts.path not in {'', '/'} or parts.query or parts.fragment:
            raise StorageError('MINIO_ENDPOINT chỉ được chứa scheme, host và port.')
        return parts.netloc, parts.scheme == 'https'

    def endpoint_summary(self) -> dict[str, Any]:
        if self.provider != 'minio':
            return {'provider': 'local', 'root': str(self.local_root)}
        endpoint, secure = self._endpoint()
        return {'provider': 'minio', 'endpoint': endpoint, 'secure': secure, 'bucket': self.bucket}

    def _client(self):
        if self._client_override is not None:
            return self._client_override
        if self._client_cache is not None:
            return self._client_cache
        endpoint, secure = self._endpoint()
        access_key = str(getattr(self.config, 'minio_access_key', '') or '').strip()
        secret_key = str(getattr(self.config, 'minio_secret_key', '') or '').strip()
        if not access_key or not secret_key:
            raise StorageError('MINIO_ACCESS_KEY/MINIO_SECRET_KEY chưa được cấu hình.')
        try:
            from minio import Minio
        except ImportError as exc:  # pragma: no cover - runtime image installs requirements-runtime.txt
            raise StorageError('Python MinIO client chưa được cài trong backend image.') from exc
        try:
            self._client_cache = Minio(
                endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure,
                region=(str(getattr(self.config, 'minio_region', '') or '').strip() or None),
                cert_check=bool(getattr(self.config, 'minio_cert_check', True)),
            )
        except Exception as exc:
            raise StorageError(f'Không khởi tạo được MinIO client: {exc.__class__.__name__}.') from exc
        return self._client_cache

    def _ensure_bucket(self, bucket: str | None = None) -> str:
        target = str(bucket or self.bucket or '').strip()
        if not target:
            raise StorageError('MINIO_BUCKET chưa được cấu hình.')
        if target in self._verified_buckets:
            return target
        client = self._client()
        try:
            exists = bool(client.bucket_exists(target))
            if not exists and bool(getattr(self.config, 'minio_auto_create_bucket', False)):
                client.make_bucket(target, region=(str(getattr(self.config, 'minio_region', '') or '').strip() or None))
                exists = True
            if not exists:
                raise StorageError(f'Bucket MinIO {target!r} không tồn tại hoặc service account không có quyền kiểm tra.')
            self._verified_buckets.add(target)
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f'Không truy cập được bucket MinIO {target!r}: {exc.__class__.__name__}.') from exc
        return target

    def _local_path_for_key(self, key: str, *, create_parent: bool = False) -> Path:
        path = (self.local_root / _normalized_key(key)).resolve()
        try:
            path.relative_to(self.local_root)
        except ValueError as exc:
            raise StorageError('Đường dẫn storage nằm ngoài LOCAL_STORAGE_PATH.') from exc
        if create_parent:
            path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _legacy_local_path(self, reference: str) -> Path:
        raw = str(reference or '').strip()
        if not raw:
            raise StorageError('Storage reference bị rỗng.')
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = self.local_root / path
        path = path.resolve()
        try:
            path.relative_to(self.local_root)
        except ValueError as exc:
            raise StorageError('Đường dẫn file nằm ngoài LOCAL_STORAGE_PATH.') from exc
        return path

    def reference_for_key(self, key: str) -> str:
        normalized = _normalized_key(key)
        if self.provider == 'minio':
            return _minio_uri(self.bucket, normalized)
        return str(self._local_path_for_key(normalized))

    def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        normalized = _normalized_key(key)
        raw = bytes(data)
        if self.provider == 'local':
            path = self._local_path_for_key(normalized, create_parent=True)
            path.write_bytes(raw)
            return str(path)
        bucket = self._ensure_bucket()
        media_type = content_type or mimetypes.guess_type(normalized)[0] or 'application/octet-stream'
        try:
            self._client().put_object(bucket, normalized, io.BytesIO(raw), len(raw), content_type=media_type)
        except Exception as exc:
            raise StorageError(f'Không ghi được object MinIO: {exc.__class__.__name__}.') from exc
        return _minio_uri(bucket, normalized)

    def put_json(self, key: str, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        return self.put_bytes(key, raw, content_type='application/json')

    def _remote_target(self, reference: str) -> tuple[str, str] | None:
        parsed = _parse_minio_uri(reference)
        if parsed:
            return parsed
        raw = str(reference or '').strip()
        if self.provider == 'minio' and raw and not Path(raw).is_absolute() and '://' not in raw:
            return self.bucket, _normalized_key(raw)
        return None

    def read_bytes(self, reference: str) -> bytes:
        remote = self._remote_target(reference)
        if not remote:
            path = self._legacy_local_path(reference)
            if not path.is_file():
                raise StorageError('File storage không còn tồn tại.')
            return path.read_bytes()
        bucket, key = remote
        self._ensure_bucket(bucket)
        response = None
        try:
            response = self._client().get_object(bucket, key)
            return response.read()
        except Exception as exc:
            raise StorageError(f'Không đọc được object MinIO: {exc.__class__.__name__}.') from exc
        finally:
            if response is not None:
                try:
                    response.close()
                    response.release_conn()
                except Exception:
                    pass

    def read_json(self, reference: str) -> dict[str, Any]:
        try:
            payload = json.loads(self.read_bytes(reference).decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StorageError('Object JSON trong storage không hợp lệ.') from exc
        if not isinstance(payload, dict):
            raise StorageError('Object JSON trong storage phải là object.')
        return payload

    def iter_bytes(self, reference: str, *, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
        remote = self._remote_target(reference)
        if not remote:
            path = self._legacy_local_path(reference)
            if not path.is_file():
                raise StorageError('File storage không còn tồn tại.')

            def local_stream() -> Iterator[bytes]:
                with path.open('rb') as handle:
                    while True:
                        chunk = handle.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk

            return local_stream()

        bucket, key = remote
        self._ensure_bucket(bucket)

        def remote_stream() -> Iterator[bytes]:
            response = None
            try:
                response = self._client().get_object(bucket, key)
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
            except Exception as exc:
                raise StorageError(f'Không stream được object MinIO: {exc.__class__.__name__}.') from exc
            finally:
                if response is not None:
                    try:
                        response.close()
                        response.release_conn()
                    except Exception:
                        pass

        return remote_stream()

    def stat(self, reference: str) -> StoredObject | None:
        remote = self._remote_target(reference)
        if not remote:
            path = self._legacy_local_path(reference)
            if not path.is_file():
                return None
            item = path.stat()
            return StoredObject(
                reference=str(path),
                key=str(path.relative_to(self.local_root)).replace('\\', '/'),
                size=int(item.st_size),
                last_modified=datetime.fromtimestamp(item.st_mtime, tz=timezone.utc),
            )
        bucket, key = remote
        self._ensure_bucket(bucket)
        try:
            item = self._client().stat_object(bucket, key)
            return StoredObject(
                reference=_minio_uri(bucket, key),
                key=key,
                size=int(getattr(item, 'size', 0) or 0),
                last_modified=getattr(item, 'last_modified', None),
            )
        except Exception as exc:
            code = str(getattr(exc, 'code', '') or '')
            if code in {'NoSuchKey', 'NoSuchObject', 'NoSuchBucket'}:
                return None
            raise StorageError(f'Không kiểm tra được object MinIO: {exc.__class__.__name__}.') from exc

    def exists(self, reference: str) -> bool:
        return self.stat(reference) is not None

    def delete(self, reference: str, *, missing_ok: bool = True) -> bool:
        remote = self._remote_target(reference)
        if not remote:
            path = self._legacy_local_path(reference)
            if not path.exists():
                if missing_ok:
                    return False
                raise StorageError('File storage không tồn tại.')
            if not path.is_file():
                raise StorageError('Storage reference không trỏ tới file.')
            path.unlink()
            return True
        bucket, key = remote
        self._ensure_bucket(bucket)
        if not missing_ok and self.stat(reference) is None:
            raise StorageError('Object MinIO không tồn tại.')
        try:
            self._client().remove_object(bucket, key)
            return True
        except Exception as exc:
            raise StorageError(f'Không xóa được object MinIO: {exc.__class__.__name__}.') from exc

    def list_objects(self, prefix: str) -> list[StoredObject]:
        normalized_prefix = _normalized_key(prefix).rstrip('/') + '/'
        if self.provider == 'local':
            base = self._local_path_for_key(normalized_prefix.rstrip('/'))
            if not base.exists():
                return []
            result: list[StoredObject] = []
            for path in base.rglob('*'):
                if not path.is_file():
                    continue
                item = path.stat()
                key = str(path.relative_to(self.local_root)).replace('\\', '/')
                result.append(StoredObject(
                    reference=str(path), key=key, size=int(item.st_size),
                    last_modified=datetime.fromtimestamp(item.st_mtime, tz=timezone.utc),
                ))
            return result
        bucket = self._ensure_bucket()
        try:
            return [
                StoredObject(
                    reference=_minio_uri(bucket, item.object_name),
                    key=item.object_name,
                    size=int(getattr(item, 'size', 0) or 0),
                    last_modified=getattr(item, 'last_modified', None),
                )
                for item in self._client().list_objects(bucket, prefix=normalized_prefix, recursive=True)
                if getattr(item, 'object_name', None)
            ]
        except Exception as exc:
            raise StorageError(f'Không liệt kê được object MinIO: {exc.__class__.__name__}.') from exc

    @contextmanager
    def local_copy(self, reference: str, *, suffix: str = '') -> Iterator[Path]:
        remote = self._remote_target(reference)
        if not remote:
            path = self._legacy_local_path(reference)
            if not path.is_file():
                raise StorageError('File storage không còn tồn tại.')
            yield path
            return
        raw = self.read_bytes(reference)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix='ai-storage-', suffix=suffix, dir='/tmp', delete=False) as handle:
                handle.write(raw)
                temp_path = Path(handle.name)
            yield temp_path
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def health(self, *, write_test: bool = False) -> dict[str, Any]:
        summary = self.endpoint_summary()
        if self.provider == 'local':
            reachable = self.local_root.exists() and self.local_root.is_dir()
            if not reachable:
                raise StorageError('LOCAL_STORAGE_PATH không tồn tại hoặc không phải thư mục.')
            summary.update({'status': 'ok', 'reachable': True})
            return summary
        bucket = self._ensure_bucket()
        summary.update({'status': 'ok', 'reachable': True, 'bucket': bucket, 'write_test': False})
        if not write_test:
            return summary
        import uuid

        key = f'_healthchecks/{uuid.uuid4().hex}.txt'
        reference = self.put_bytes(key, b'ai-server-minio-ok', content_type='text/plain')
        try:
            if self.read_bytes(reference) != b'ai-server-minio-ok':
                raise StorageError('MinIO write/read smoke test trả về dữ liệu không khớp.')
        finally:
            self.delete(reference, missing_ok=True)
        summary['write_test'] = True
        return summary


def get_object_storage() -> ObjectStorage:
    return ObjectStorage(settings)
