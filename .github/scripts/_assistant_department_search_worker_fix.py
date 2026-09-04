from pathlib import Path
import re

page_path = Path('frontend/app/bank/_components/pages/DepartmentsPage.tsx')
page = page_path.read_text()

old_states = """  const [subjectResults, setSubjectResults] = useState<Subject[]>([])\n  const [subjectSearching, setSubjectSearching] = useState(false)\n  const [subjectSearchError, setSubjectSearchError] = useState('')\n  const [subjectDepartmentFilter, setSubjectDepartmentFilter] = useState('all')\n"""
new_states = """  const [subjectResults, setSubjectResults] = useState<Subject[]>([])\n"""
if old_states not in page:
    raise SystemExit('department search state marker not found')
page = page.replace(old_states, new_states, 1)

old_effect = """  useEffect(() => {\n    const query = search.trim()\n    if (query.length < 2) {\n      setSubjectResults([])\n      setSubjectSearching(false)\n      setSubjectSearchError('')\n      return\n    }\n    const controller = new AbortController()\n    const timer = window.setTimeout(() => {\n      setSubjectSearching(true)\n      setSubjectSearchError('')\n      searchSubjects(headers, { query, signal: controller.signal })\n        .then(setSubjectResults)\n        .catch((error) => {\n          if (controller.signal.aborted) return\n          setSubjectSearchError(error instanceof Error ? error.message : 'Không thể tìm môn học.')\n        })\n        .finally(() => {\n          if (!controller.signal.aborted) setSubjectSearching(false)\n        })\n    }, 250)\n    return () => {\n      window.clearTimeout(timer)\n      controller.abort()\n    }\n  }, [headers, search])\n\n  const visible = useMemo(() => summaries.filter(({ department, stats }) => (\n    matchesSearch(`${department.code} ${department.name}`, search) && bankStatusMatches(stats, statusFilter)\n  )), [search, statusFilter, summaries])\n\n  const totalPages = Math.max(1, Math.ceil(visible.length / tableState.pageSize))\n  const safePage = Math.min(tableState.page, totalPages)\n  const pageRows = visible.slice((safePage - 1) * tableState.pageSize, safePage * tableState.pageSize)\n  const departmentById = useMemo(() => new Map(\n    summaries.map(({ department }) => [department.id, department]),\n  ), [summaries])\n  const visibleSubjectResults = useMemo(() => subjectResults.filter((subject) => (\n    subjectDepartmentFilter === 'all' || subject.department_id === subjectDepartmentFilter\n  )), [subjectDepartmentFilter, subjectResults])\n"""
new_effect = """  useEffect(() => {\n    const query = search.trim()\n    if (query.length < 2) {\n      setSubjectResults([])\n      return\n    }\n    const controller = new AbortController()\n    const timer = window.setTimeout(() => {\n      searchSubjects(headers, { query, signal: controller.signal })\n        .then((rows) => { if (!controller.signal.aborted) setSubjectResults(rows) })\n        .catch(() => { if (!controller.signal.aborted) setSubjectResults([]) })\n    }, 250)\n    return () => {\n      window.clearTimeout(timer)\n      controller.abort()\n    }\n  }, [headers, search])\n\n  const subjectDepartmentIds = useMemo(\n    () => new Set(subjectResults.map((subject) => subject.department_id)),\n    [subjectResults],\n  )\n  const visible = useMemo(() => summaries.filter(({ department, stats }) => (\n    (\n      matchesSearch(`${department.code} ${department.name}`, search)\n      || (search.trim().length >= 2 && subjectDepartmentIds.has(department.id))\n    )\n    && bankStatusMatches(stats, statusFilter)\n  )), [search, statusFilter, subjectDepartmentIds, summaries])\n\n  const totalPages = Math.max(1, Math.ceil(visible.length / tableState.pageSize))\n  const safePage = Math.min(tableState.page, totalPages)\n  const pageRows = visible.slice((safePage - 1) * tableState.pageSize, safePage * tableState.pageSize)\n"""
if old_effect not in page:
    raise SystemExit('department search effect/visible marker not found')
page = page.replace(old_effect, new_effect, 1)

pattern = re.compile(
    r'\n    <section className="subject-quick-search" aria-label="Tìm bộ môn hoặc môn học">.*?\n    </section>\n\n    (<section className="bank-hierarchy-panel" aria-label="Danh sách bộ môn">)',
    re.S,
)
page, count = pattern.subn(r'\n    \1', page, count=1)
if count != 1:
    raise SystemExit(f'expected one standalone quick-search section, got {count}')

if '        hideSearch\n' not in page:
    raise SystemExit('BankTableToolbar hideSearch marker not found')
page = page.replace('        hideSearch\n', '', 1)

if 'subject-quick-search' in page:
    raise SystemExit('standalone subject quick search still present in DepartmentsPage')
if 'searchSubjects(headers' not in page or 'subjectDepartmentIds.has(department.id)' not in page:
    raise SystemExit('subject search behavior was not retained inside table filtering')
if 'hideSearch' in page:
    raise SystemExit('table toolbar search is still hidden')
page_path.write_text(page)

academic_path = Path('backend/app/services/academic_service.py')
academic = academic_path.read_text()
old_contract = """        if contract and str(contract) != self.CONNECTOR_MIN_CONTRACT_VERSION:\n            raise RuntimeError(\n                f'Open edX Connector contract không khớp ({contract}). Yêu cầu {self.CONNECTOR_MIN_CONTRACT_VERSION}. '\n                'Dừng ghi snapshot để tránh ghi đè dữ liệu đúng bằng payload sai contract.'\n            )\n"""
new_contract = """        if contract and not self._version_at_least(contract, self.CONNECTOR_MIN_CONTRACT_VERSION):\n            raise RuntimeError(\n                f'Open edX Connector contract quá cũ ({contract}). Yêu cầu tối thiểu {self.CONNECTOR_MIN_CONTRACT_VERSION}. '\n                'Dừng ghi snapshot để tránh ghi đè dữ liệu đúng bằng payload sai contract.'\n            )\n"""
if old_contract not in academic:
    raise SystemExit('connector contract equality marker not found')
academic = academic.replace(old_contract, new_contract, 1)
academic_path.write_text(academic)

test_path = Path('backend/app/tests/test_academic_connector_contract_compat.py')
test_path.write_text("""import pytest\n\nfrom app.services.academic_service import AcademicService\n\n\ndef _payload(*, runtime: str, contract: str) -> dict:\n    return {\n        'ok': True,\n        'connector_version': runtime,\n        'connector_contract_version': contract,\n        'progress_contract': {\n            'denominator': 'reachable_sequential_subsections',\n            'numerator': 'studentmodule_sequential_position_rows',\n            'ignored_studentmodule_types': ['itembank', 'problem', 'video'],\n        },\n    }\n\n\ndef _service() -> AcademicService:\n    return AcademicService.__new__(AcademicService)\n\n\ndef test_connector_accepts_newer_compatible_contract_version():\n    service = _service()\n    service._validate_connector_learning_contract(\n        _payload(runtime='25.9.16.5.99', contract='learning-sync/v25.9.16.5.99'),\n        course_id='course-v1:FPL+MEC229+SU26',\n    )\n\n\ndef test_connector_rejects_contract_older_than_minimum():\n    service = _service()\n    with pytest.raises(RuntimeError, match='contract quá cũ'):\n        service._validate_connector_learning_contract(\n            _payload(runtime='25.9.16.5.99', contract='learning-sync/v25.9.16.5.97'),\n            course_id='course-v1:FPL+MEC229+SU26',\n        )\n\n\ndef test_connector_still_rejects_unsafe_progress_semantics():\n    service = _service()\n    payload = _payload(runtime='25.9.16.5.99', contract='learning-sync/v25.9.16.5.99')\n    payload['progress_contract']['denominator'] = 'legacy_block_count'\n    with pytest.raises(RuntimeError, match='progress_contract không an toàn'):\n        service._validate_connector_learning_contract(payload, course_id='course-v1:FPL+MEC229+SU26')\n""")
