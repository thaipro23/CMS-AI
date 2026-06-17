"""v25.9.16.2.13 semester management page seed

Revision ID: 0039_v25_9_16_2_13_terms
Revises: 0038_v25_9_16_2_12_premises
Create Date: 2026-06-17
"""
from __future__ import annotations

import json
from alembic import op
import sqlalchemy as sa

revision = '0039_v25_9_16_2_13_terms'
down_revision = '0038_v25_9_16_2_12_premises'
branch_labels = None
depends_on = None

TERMS = [{'id': '5ad7f095-113f-599c-a5a0-d720fe5f509e', 'ap_term_id': None, 'term_code': 'Summer 2026', 'term_name': 'Summer 2026', 'branch': 'poly', 'start_date': '2026-05-11', 'end_date': '2026-08-15', 'active': True, 'metadata_json': {'source': 'acms_html_semester', 'import_version': 'v25.9.16.2.13'}}, {'id': 'b581386a-6680-5bf4-9553-87691d978512', 'ap_term_id': None, 'term_code': 'Summer 2026', 'term_name': 'Summer 2026', 'branch': 'ptcd', 'start_date': '2026-04-28', 'end_date': '2026-08-31', 'active': True, 'metadata_json': {'source': 'acms_html_semester', 'import_version': 'v25.9.16.2.13'}}]

BLOCKS = [{'id': '7e61a2ec-0cc3-59e7-b86d-d1379a8612ec', 'term_id': '5ad7f095-113f-599c-a5a0-d720fe5f509e', 'ap_block_id': None, 'block_code': 'Block 1', 'block_name': 'Block 1', 'start_date': '2026-05-11', 'end_date': '2026-06-20', 'sort_order': 1, 'active': True, 'metadata_json': {'source': 'acms_html_semester', 'import_version': 'v25.9.16.2.13'}}, {'id': '4e5d1729-9b0f-5ad4-9072-d2e560dcfcd0', 'term_id': '5ad7f095-113f-599c-a5a0-d720fe5f509e', 'ap_block_id': None, 'block_code': 'Block 2', 'block_name': 'Block 2', 'start_date': '2026-06-29', 'end_date': '2026-08-15', 'sort_order': 2, 'active': True, 'metadata_json': {'source': 'acms_html_semester', 'import_version': 'v25.9.16.2.13'}}, {'id': 'aca3a7cc-58d4-5fdf-997a-28d8e658644a', 'term_id': 'b581386a-6680-5bf4-9553-87691d978512', 'ap_block_id': None, 'block_code': 'Block1', 'block_name': 'Block1', 'start_date': '2026-04-28', 'end_date': '2026-06-18', 'sort_order': 1, 'active': True, 'metadata_json': {'source': 'acms_html_semester', 'import_version': 'v25.9.16.2.13'}}, {'id': 'ab6cd8b1-a967-564c-9efe-4f4983a4f944', 'term_id': 'b581386a-6680-5bf4-9553-87691d978512', 'ap_block_id': None, 'block_code': 'Block2', 'block_name': 'Block2', 'start_date': '2026-06-19', 'end_date': '2026-08-31', 'sort_order': 2, 'active': True, 'metadata_json': {'source': 'acms_html_semester', 'import_version': 'v25.9.16.2.13'}}]

def _dt(value: str):
    return sa.text(f"'{value} 00:00:00'")

def upgrade() -> None:
    conn = op.get_bind()
    now = sa.func.now()
    for item in TERMS:
        conn.execute(sa.text("""
            INSERT INTO academic_terms (id, ap_term_id, term_code, term_name, branch, start_date, end_date, active, metadata_json, created_at, updated_at)
            VALUES (:id, :ap_term_id, :term_code, :term_name, :branch, CAST(:start_date AS timestamp), CAST(:end_date AS timestamp), :active, CAST(:metadata_json AS json), NOW(), NOW())
            ON CONFLICT (term_code, branch) DO UPDATE SET
                term_name = EXCLUDED.term_name,
                start_date = EXCLUDED.start_date,
                end_date = EXCLUDED.end_date,
                active = TRUE,
                metadata_json = EXCLUDED.metadata_json,
                updated_at = NOW()
        """), {**item, 'metadata_json': json.dumps(item['metadata_json'], ensure_ascii=False)})
    term_ids = {item['branch']: conn.execute(sa.text("SELECT id FROM academic_terms WHERE term_code = :code AND branch = :branch"), {'code': item['term_code'], 'branch': item['branch']}).scalar() for item in TERMS}
    for item in BLOCKS:
        branch = 'ptcd' if item['block_code'] in {'Block1', 'Block2'} else 'poly'
        term_id = term_ids.get(branch) or item['term_id']
        params = {**item, 'term_id': term_id, 'metadata_json': json.dumps(item['metadata_json'], ensure_ascii=False)}
        conn.execute(sa.text("""
            INSERT INTO academic_blocks (id, term_id, ap_block_id, block_code, block_name, start_date, end_date, sort_order, active, metadata_json, created_at, updated_at)
            VALUES (:id, :term_id, :ap_block_id, :block_code, :block_name, CAST(:start_date AS timestamp), CAST(:end_date AS timestamp), :sort_order, :active, CAST(:metadata_json AS json), NOW(), NOW())
            ON CONFLICT (term_id, block_code) DO UPDATE SET
                block_name = EXCLUDED.block_name,
                start_date = EXCLUDED.start_date,
                end_date = EXCLUDED.end_date,
                sort_order = EXCLUDED.sort_order,
                active = TRUE,
                metadata_json = EXCLUDED.metadata_json,
                updated_at = NOW()
        """), params)

def downgrade() -> None:
    conn = op.get_bind()
    term_ids = [row[0] for row in conn.execute(sa.text("SELECT id FROM academic_terms WHERE term_code = 'Summer 2026' AND metadata_json ->> 'source' = 'acms_html_semester'")).fetchall()]
    for term_id in term_ids:
        conn.execute(sa.text("DELETE FROM academic_blocks WHERE term_id = :term_id AND metadata_json ->> 'source' = 'acms_html_semester'"), {'term_id': term_id})
    conn.execute(sa.text("DELETE FROM academic_terms WHERE term_code = 'Summer 2026' AND metadata_json ->> 'source' = 'acms_html_semester'"))
