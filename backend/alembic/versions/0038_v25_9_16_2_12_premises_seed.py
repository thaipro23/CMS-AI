"""v25.9.16.2.12 seed ACMS premises master data

Revision ID: 0038_v25_9_16_2_12_premises
Revises: 0037_v25_9_16_2_11_campus
Create Date: 2026-06-17
"""
from __future__ import annotations

import json
from alembic import op
import sqlalchemy as sa

revision = '0038_v25_9_16_2_12_premises'
down_revision = '0037_v25_9_16_2_11_campus'
branch_labels = None
depends_on = None

PREMISES = [
    {
        "id": "fc64c54d-8baa-596a-9204-c73583ab4975",
        "campus_code": "pa",
        "campus_name": "Thanh Hóa",
        "branch": "poly",
        "active": True,
        "sort_order": 1,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "PA",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "f60b5e9e-4b04-5dd2-a226-a40c32a27292",
        "campus_code": "pc",
        "campus_name": "Cần thơ",
        "branch": "poly",
        "active": True,
        "sort_order": 2,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "PC",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "86ff188d-361e-5b4c-94fd-3762167a7aba",
        "campus_code": "pd",
        "campus_name": "Đà Nẵng",
        "branch": "poly",
        "active": True,
        "sort_order": 3,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "PD",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "9a8959a9-7381-501d-9022-926014978a25",
        "campus_code": "ph",
        "campus_name": "Hà Nội",
        "branch": "poly",
        "active": True,
        "sort_order": 4,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "PH",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "19a56141-94e3-57ad-8ccc-27bb6f1da952",
        "campus_code": "pi",
        "campus_name": "Đồng Nai",
        "branch": "poly",
        "active": True,
        "sort_order": 5,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "PI",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "5655bc62-e32f-5d6f-9725-3e43a25ea16f",
        "campus_code": "pk",
        "campus_name": "Tây Nguyên",
        "branch": "poly",
        "active": True,
        "sort_order": 6,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "PK",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "d7d3e42b-2cae-5ed7-8f8e-e44993b9f92d",
        "campus_code": "pn",
        "campus_name": "Hà Nam",
        "branch": "poly",
        "active": True,
        "sort_order": 7,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "PN",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "79f32c2d-624d-5ce9-be75-9b2b0edc91bd",
        "campus_code": "pp",
        "campus_name": "Hải Phòng",
        "branch": "poly",
        "active": True,
        "sort_order": 8,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "PP",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "d513370f-467a-555f-ab4a-845253b6bb80",
        "campus_code": "ps",
        "campus_name": "TP. HCM",
        "branch": "poly",
        "active": True,
        "sort_order": 9,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "PS",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "e4bcd998-03b3-59b5-9f5a-a320151341a1",
        "campus_code": "pt",
        "campus_name": "Thái Nguyên",
        "branch": "poly",
        "active": True,
        "sort_order": 10,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "PT",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "1de7c36b-0285-55ac-85fd-809f3fc63b03",
        "campus_code": "py",
        "campus_name": "Quy Nhơn",
        "branch": "poly",
        "active": True,
        "sort_order": 11,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "PY",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "f565ef0b-9508-5f25-90a0-fddf8ec22257",
        "campus_code": "ta",
        "campus_name": "Nam Định - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 12,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TA",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "84b7cc61-af37-59ae-b976-88e6ef920ceb",
        "campus_code": "tb",
        "campus_name": "Đồng Nai - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 13,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TB",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "a4c38c59-881d-5002-a33c-55a0c22e4fdf",
        "campus_code": "tc",
        "campus_name": "Cần Thơ - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 14,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TC",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "f65d1efa-f6a8-5a6e-bb5d-55b0d0e8223f",
        "campus_code": "td",
        "campus_name": "Đà Nẵng - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 15,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TD",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "d2faa961-9cfd-54bc-a810-38ba728dfb66",
        "campus_code": "tg",
        "campus_name": "Bắc Giang - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 16,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TG",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "234a4e29-4d92-5d2d-80d0-21386472c3a5",
        "campus_code": "th",
        "campus_name": "Hà Nội - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 17,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TH",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "4b20728c-a46c-5355-9cf5-22143a54eaf6",
        "campus_code": "ti",
        "campus_name": "Bình Định - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 18,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TI",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "4862d7d4-4613-5df2-b369-a6c04bb25306",
        "campus_code": "tk",
        "campus_name": "Tây Nguyên - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 19,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TK",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "ca13be59-74d3-51e9-ad1e-b991b9f25fb7",
        "campus_code": "tl",
        "campus_name": "Vĩnh Phúc - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 20,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TL",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "51e68105-c370-53c5-8f92-aa9cd9a875f0",
        "campus_code": "tm",
        "campus_name": "Hà Nam - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 21,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TM",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "c69efb1a-4ca0-5e0b-929e-eb9e8a9c2348",
        "campus_code": "tn",
        "campus_name": "Bình Phước - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 22,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TN",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "768d1b3e-6948-54fc-95dc-b616787e4daf",
        "campus_code": "to",
        "campus_name": "Thanh Hóa - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 23,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TO",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "9804c143-3b63-54be-a29d-4fe9f323f382",
        "campus_code": "tp",
        "campus_name": "Hải Phòng - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 24,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TP",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "0c589400-9c5f-5d62-9d6d-48f29e03383d",
        "campus_code": "tq",
        "campus_name": "Quảng Nam - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 25,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TQ",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "e80501ff-2366-55e1-b103-be46b34ea40c",
        "campus_code": "ts",
        "campus_name": "Hồ Chí Minh - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 26,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TS",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "d020ef70-8c72-5ab4-b121-345e67d524b3",
        "campus_code": "tt",
        "campus_name": "Huế - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 27,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TT",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "1a016939-6370-5e94-bb10-b8196885f038",
        "campus_code": "tu",
        "campus_name": "Thái Nguyên - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 28,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TU",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "ae9f5626-91f5-5899-b239-891ea627a4f0",
        "campus_code": "tv",
        "campus_name": "Bình Dương - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 29,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TV",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "033e5f61-c9e0-5316-9f75-c76d6effbb42",
        "campus_code": "tw",
        "campus_name": "Nghệ An - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 30,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TW",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "519fbcbd-3c7e-548a-b7ef-2f6cb21790ea",
        "campus_code": "tx",
        "campus_name": "Nha Trang Khánh Hòa - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 31,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TX",
            "import_version": "v25.9.16.2.12"
        }
    },
    {
        "id": "e2bbca06-da8a-5780-a9f4-b3cc71b42a6e",
        "campus_code": "ty",
        "campus_name": "Bà Rịa Vũng Tàu - PTCD",
        "branch": "ptcd",
        "active": True,
        "sort_order": 32,
        "metadata_json": {
            "source": "acms_html_premises",
            "acms_code": "TY",
            "import_version": "v25.9.16.2.12"
        }
    }
]


def upgrade() -> None:
    conn = op.get_bind()
    table = sa.table(
        'academic_campuses',
        sa.column('id', sa.String()),
        sa.column('campus_code', sa.String()),
        sa.column('campus_name', sa.String()),
        sa.column('branch', sa.String()),
        sa.column('active', sa.Boolean()),
        sa.column('sort_order', sa.Integer()),
        sa.column('metadata_json', sa.JSON()),
    )
    for item in PREMISES:
        existing = conn.execute(
            sa.text('SELECT id FROM academic_campuses WHERE campus_code = :code AND branch = :branch'),
            {'code': item['campus_code'], 'branch': item['branch']},
        ).first()
        if existing:
            conn.execute(
                sa.text(
                    "UPDATE academic_campuses "
                    "SET campus_name = :name, active = true, sort_order = :sort_order, "
                    "metadata_json = (COALESCE(metadata_json, '{}'::json)::jsonb || CAST(:metadata_json AS jsonb))::json, "
                    "updated_at = NOW() "
                    "WHERE campus_code = :code AND branch = :branch"
                ),
                {
                    'name': item['campus_name'],
                    'sort_order': item['sort_order'],
                    'metadata_json': json.dumps(item['metadata_json'], ensure_ascii=False),
                    'code': item['campus_code'],
                    'branch': item['branch'],
                },
            )
        else:
            op.bulk_insert(table, [item])


def downgrade() -> None:
    conn = op.get_bind()
    for item in PREMISES:
        conn.execute(
            sa.text("DELETE FROM academic_campuses WHERE campus_code = :code AND branch = :branch AND metadata_json ->> 'source' = 'acms_html_premises'"),
            {'code': item['campus_code'], 'branch': item['branch']},
        )
