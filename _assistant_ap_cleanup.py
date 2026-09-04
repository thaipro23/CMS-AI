from pathlib import Path

# Clean stale comments / old host assumptions from canonical runtime source.
p = Path('backend/app/core/config.py')
s = p.read_text()
s = s.replace(
    "    # Subject catalog source of truth. Discovery always calls this endpoint with\n    # branch=poly and the selected term_name. The requested UI branch is retained\n    # as metadata only because AP's ptcd catalog has historically been noisy.\n",
    "    # Canonical internal CMS API: global subject catalog, product-scoped campuses,\n    # and POSTed class/student data. These endpoints are keyless.\n",
)
s = s.replace(
    "    # TLS verification mode for AP integrations other than api_v2.poly.edu.vn.\n    # api_v2.poly.edu.vn is an approved host-specific exception and always uses\n    # verify=False because its served certificate currently mismatches the hostname.\n    # strict: verify CA chain + hostname (default for every other host).\n    # chain_only: verify CA chain but skip hostname check.\n    # off: disable TLS verification for the configured AP host.\n",
    "    # Internal API uses normal HTTPS verification. chain_only/off remain emergency\n    # deployment knobs only; there is no hostname-specific TLS bypass.\n",
)
s = s.replace(
    "    # (no valid student username in student/students array) are ignored and do\n    # not create subject/class/teacher/student rows. The /get-course catalog is\n    # used for discovery; subjects are persisted only when required by the flow.\n",
    "    # (no valid student username in student/students array) are ignored and do\n    # not create subject/class/teacher/student rows. /get-all-subject is discovery\n    # only; subjects are persisted when required by the selected sync flow.\n",
)
s = s.replace(
    "    # Cache the AP /get-course discovery response into a local JSON file so one\n",
    "    # Cache the internal /get-all-subject response into a local JSON file so one\n",
)
p.write_text(s)

p = Path('backend/app/services/ap_academic_sync.py')
s = p.read_text()
s = s.replace('from urllib.parse import urlparse\n', '')
s = s.replace(
    "cache_scope = f'{self.base_url}|{endpoint}|discovery-branch=poly'",
    "cache_scope = f'{self.base_url}|{endpoint}|branch={_lower(branch) or \"poly\"}'",
)
s = s.replace(
    '        # Optional emergency fallback only. Normal production flow uses api_v2 /get-course.\n',
    '        # Optional emergency fallback only. Normal flow uses keyless /get-all-subject.\n',
)
s = s.replace(
    "                        'Hãy kiểm tra API key/kết nối AP hoặc chọn phạm vi Theo môn với mã môn cụ thể. '\n",
    "                        'Hãy kiểm tra kết nối API nội bộ hoặc chọn phạm vi Theo môn với mã môn cụ thể. '\n",
)
old = """        if scope == 'all':
            configured = requested or [item['value'] for item in self._campus_master_values(branch=branch)]
            if not configured:
                raise RuntimeError('sync_scope=all cần danh sách cơ sở đang dùng trong /premises. Vào trang Cơ sở, thêm hoặc bật cơ sở cho đúng hệ rồi chạy lại.')
            return configured
"""
new = """        if scope == 'all':
            if requested:
                return requested
            try:
                remote = APAcademicClient().get_campuses(branch=branch)
                configured = [_lower(item.get('campus_code')) for item in remote if _lower(item.get('campus_code'))]
            except Exception:
                configured = [item['value'] for item in self._campus_master_values(branch=branch)]
            if not configured:
                raise RuntimeError('Không tải được danh sách cơ sở từ API nội bộ và chưa có danh mục cơ sở dự phòng.')
            return list(dict.fromkeys(configured))
"""
if old not in s:
    raise RuntimeError('resolve campuses block not found')
s = s.replace(old, new, 1)
p.write_text(s)

# Old private DNS override belongs to the retired api_v2 gateway.
for name in ('docker-compose.prod.yml', 'docker-compose.yml'):
    path = Path(name)
    if path.exists():
        text = path.read_text().replace('    - api_v2.poly.edu.vn:10.2.1.35\n', '')
        path.write_text(text)

print('AP runtime cleanup applied')
