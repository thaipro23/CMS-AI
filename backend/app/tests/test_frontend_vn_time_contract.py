from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TIME = ROOT / 'frontend/lib/time.ts'


def test_naive_backend_iso_timestamps_are_interpreted_as_utc_before_vietnam_formatting():
    source = TIME.read_text(encoding='utf-8')
    assert 'function parseServerDateTime' in source
    assert 'datetime.utcnow()' in source
    assert 'naiveIsoUtc' in source
    assert "${raw}Z" in source
    assert 'parseServerDateTime(raw)' in source
