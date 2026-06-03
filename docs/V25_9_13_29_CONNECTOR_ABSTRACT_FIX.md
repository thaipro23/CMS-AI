# v25.9.13.29 - OpenEdX Connector Abstract Fix

Sửa lỗi khi bấm đồng bộ:

```txt
TypeError: Can't instantiate abstract class RealOpenEdXConnector without an implementation for abstract method 'publish_problem_olx'
```

Nguyên nhân: trong `backend/app/modules/openedx_connector/real.py`, các method `verify_library_problem`, `delete_library_problem`, `publish_problem_olx` bị lệch indent ra ngoài class `RealOpenEdXConnector` sau khi merge các nâng cấp publish/reconciliation. Python compile vẫn qua, nhưng ABC coi `RealOpenEdXConnector` chưa implement `publish_problem_olx`, nên factory không instantiate được connector.

Đã sửa:

- Đưa `verify_library_problem` vào trong class.
- Đưa `delete_library_problem` vào trong class.
- Đưa `publish_problem_olx` vào đúng cấp class.
- Nâng version lên `25.9.13.29`.

Cách chạy:

```bash
docker compose down
docker compose build --no-cache backend worker frontend
docker compose up
```

Không cần build lại Open edX/CMS nếu chỉ sửa lỗi sync này.
