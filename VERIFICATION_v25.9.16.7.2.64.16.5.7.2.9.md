# Verification — v25.9.16.7.2.64.16.5.7.2.9

- Python compile: PASS.
- Batch 33–35.3.2 selected regression: 41 passed.
- Current uploaded 26-column Vietnamese Udemy CSV: PASS.
  - parser_format=item_rows
  - header_row=1
  - data rows read=7
  - learner records=3
  - parser issues=0
- CSV and XLSX header-based mapping: PASS.
- Reordered `ID bên ngoài`: PASS.
- Legacy 25-column fallback: PASS.
- No Alembic migration after 0057.
