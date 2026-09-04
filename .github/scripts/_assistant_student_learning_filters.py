from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f'{label}: marker not found')
    return text.replace(old, new, 1)


service_path = Path('backend/app/services/academic_service.py')
service = service_path.read_text()

helper_marker = "    def _learning_summary_by_class_ids(self, class_ids: list[str], course_by_class: dict[str, str | None] | None = None) -> dict[str, dict[str, Any]]:\n"
helper = """    def _learning_issue_counts_from_snapshots(self, snapshots: list[AcademicStudentLearningSnapshot]) -> dict[str, int]:
        \"\"\"Count actionable learner states without turning missing snapshots into fake learner issues.

        The subject/class filters are phrased as \"Có sinh viên ...\", so they must
        match when at least one known learner is in that state. Aggregate averages
        are not sufficient: one learner can have a low grade while the subject
        average is still high, and one learner can be inactive while classmates
        are already studying.
        \"\"\"
        counts = {
            'not_enrolled': 0,
            'no_activity': 0,
            'low_progress': 0,
            'low_grade': 0,
            'sync_error': 0,
        }
        sync_error_statuses = {'failed', 'missing_user', 'inactive_user', 'unknown'}
        for snapshot in snapshots or []:
            enrollment_status = str(snapshot.enrollment_status or '').strip().lower()
            if enrollment_status in sync_error_statuses:
                counts['sync_error'] += 1
                continue
            if enrollment_status != 'enrolled':
                counts['not_enrolled'] += 1
                continue
            if not self._snapshot_has_learning_activity(snapshot):
                counts['no_activity'] += 1
                continue
            progress = self._snapshot_progress_percent(snapshot)
            grade = self._snapshot_grade_percent(snapshot)
            if progress is not None and progress < self._low_progress_threshold():
                counts['low_progress'] += 1
            if grade is not None and grade < self._low_grade_threshold():
                counts['low_grade'] += 1
        return counts

"""
if '_learning_issue_counts_from_snapshots' not in service:
    service = replace_once(service, helper_marker, helper + helper_marker, 'learning issue helper')

alerts_marker = "        alerts = entry.get('learning_alerts') or []\n        if status == 'no_course_map':\n"
alerts_new = "        alerts = entry.get('learning_alerts') or []\n        issue_counts_raw = entry.get('learning_status_counts')\n        has_issue_counts = isinstance(issue_counts_raw, dict)\n        issue_counts = issue_counts_raw if has_issue_counts else {}\n        if status == 'no_course_map':\n"
service = replace_once(service, alerts_marker, alerts_new, 'filter issue counts')

replacements = [
    (
        "        if status == 'not_fully_enrolled':\n            return total > 0 and enrolled < total\n",
        "        if status == 'not_fully_enrolled':\n            if has_issue_counts:\n                return int(issue_counts.get('not_enrolled') or 0) > 0\n            return total > 0 and enrolled < total\n",
        'not enrolled filter',
    ),
    (
        "        if status == 'no_activity':\n            return total > 0 and synced > 0 and active == 0\n",
        "        if status == 'no_activity':\n            if has_issue_counts:\n                return int(issue_counts.get('no_activity') or 0) > 0\n            return total > 0 and synced > 0 and active == 0\n",
        'no activity filter',
    ),
    (
        "        if status == 'low_progress':\n            return isinstance(avg_progress, (int, float)) and avg_progress < self._low_progress_threshold()\n",
        "        if status == 'low_progress':\n            if has_issue_counts:\n                return int(issue_counts.get('low_progress') or 0) > 0\n            return isinstance(avg_progress, (int, float)) and avg_progress < self._low_progress_threshold()\n",
        'low progress filter',
    ),
    (
        "        if status == 'low_grade':\n            return isinstance(avg_grade, (int, float)) and avg_grade < self._low_grade_threshold()\n",
        "        if status == 'low_grade':\n            if has_issue_counts:\n                return int(issue_counts.get('low_grade') or 0) > 0\n            return isinstance(avg_grade, (int, float)) and avg_grade < self._low_grade_threshold()\n",
        'low grade filter',
    ),
    (
        "        if status == 'sync_error':\n            return any('lỗi' in str(item).lower() for item in alerts)\n",
        "        if status == 'sync_error':\n            if has_issue_counts:\n                return int(issue_counts.get('sync_error') or 0) > 0\n            return any('lỗi' in str(item).lower() for item in alerts)\n",
        'sync error filter',
    ),
]
for old, new, label in replacements:
    service = replace_once(service, old, new, label)

summary_marker = "                'learning_not_enrolled_count': max(0, total - enrolled),\n                'learning_avg_progress_percent': avg_progress,\n"
summary_new = "                'learning_not_enrolled_count': max(0, total - enrolled),\n                'learning_status_counts': self._learning_issue_counts_from_snapshots(bucket['snapshots']),\n                'learning_avg_progress_percent': avg_progress,\n"
summary_count = service.count(summary_marker)
if summary_count != 2:
    raise SystemExit(f'learning summary marker: expected 2 occurrences, got {summary_count}')
service = service.replace(summary_marker, summary_new)
service_path.write_text(service)

schema_path = Path('backend/app/schemas/academic.py')
schema = schema_path.read_text()
schema_marker = "    learning_not_enrolled_count: int = 0\n    learning_avg_progress_percent: float | None = None\n"
schema_new = "    learning_not_enrolled_count: int = 0\n    learning_status_counts: dict[str, int] = Field(default_factory=dict)\n    learning_avg_progress_percent: float | None = None\n"
schema = replace_once(schema, schema_marker, schema_new, 'academic subject schema')
schema_path.write_text(schema)

types_path = Path('frontend/types/index.ts')
types = types_path.read_text()
types_marker = "  learning_not_enrolled_count?: number\n  learning_avg_progress_percent?: number | null\n"
types_count = types.count(types_marker)
if types_count < 1:
    raise SystemExit('frontend learning type marker not found')
types = types.replace(
    types_marker,
    "  learning_not_enrolled_count?: number\n  learning_status_counts?: Record<string, number>\n  learning_avg_progress_percent?: number | null\n",
)
types_path.write_text(types)

page_path = Path('frontend/app/student-management/StudentManagementPlatformPage.tsx')
page = page_path.read_text()
old_options = """              {isCms ? <>
                <option value=\"no_course_map\">Chưa ghép course</option>
                <option value=\"cms_not_synced\">Chưa đồng bộ CMS</option>
                <option value=\"no_learning_data\">Chưa có progress CMS</option>
              </> : <>
"""
new_options = """              {isCms ? <>
                <option value=\"not_fully_enrolled\">Có sinh viên chưa ghi danh</option>
                <option value=\"no_activity\">Có sinh viên chưa học</option>
                <option value=\"low_progress\">Có sinh viên tiến độ thấp</option>
                <option value=\"low_grade\">Có sinh viên điểm thấp</option>
              </> : <>
"""
page = replace_once(page, old_options, new_options, 'CMS learner-centric filter options')
page_path.write_text(page)

test_path = Path('backend/app/tests/test_student_management_learning_filters.py')
test_path.write_text("""from types import SimpleNamespace

from app.services.academic_service import AcademicService


def _service() -> AcademicService:
    service = AcademicService.__new__(AcademicService)
    service._snapshot_has_learning_activity = lambda snapshot: bool(snapshot.active)
    service._snapshot_progress_percent = lambda snapshot: snapshot.progress
    service._snapshot_grade_percent = lambda snapshot: snapshot.grade
    service._low_progress_threshold = lambda: 50.0
    service._low_grade_threshold = lambda: 50.0
    return service


def _snapshot(*, enrollment='enrolled', active=True, progress=80.0, grade=80.0):
    return SimpleNamespace(
        enrollment_status=enrollment,
        active=active,
        progress=progress,
        grade=grade,
    )


def test_issue_counts_are_per_student_not_subject_average():
    service = _service()
    counts = service._learning_issue_counts_from_snapshots([
        _snapshot(enrollment='not_enrolled', active=False, progress=None, grade=None),
        _snapshot(active=False, progress=0.0, grade=None),
        _snapshot(active=True, progress=35.0, grade=85.0),
        _snapshot(active=True, progress=90.0, grade=40.0),
        _snapshot(active=True, progress=90.0, grade=90.0),
    ])
    assert counts == {
        'not_enrolled': 1,
        'no_activity': 1,
        'low_progress': 1,
        'low_grade': 1,
        'sync_error': 0,
    }


def test_missing_or_failed_sync_is_not_misreported_as_not_enrolled():
    service = _service()
    counts = service._learning_issue_counts_from_snapshots([
        _snapshot(enrollment='unknown', active=False, progress=None, grade=None),
        _snapshot(enrollment='failed', active=False, progress=None, grade=None),
    ])
    assert counts['not_enrolled'] == 0
    assert counts['sync_error'] == 2


def test_subject_filter_matches_when_any_student_has_issue_even_if_averages_are_good():
    service = _service()
    entry = {
        'student_count': 30,
        'learning_enrolled_count': 29,
        'learning_synced_count': 30,
        'learning_active_count': 29,
        'learning_avg_progress_percent': 88.0,
        'learning_avg_grade_percent': 82.0,
        'learning_alerts': [],
        'learning_status_counts': {
            'not_enrolled': 1,
            'no_activity': 1,
            'low_progress': 1,
            'low_grade': 1,
            'sync_error': 0,
        },
    }
    assert service._entry_matches_learning_list_filter(entry, 'not_fully_enrolled') is True
    assert service._entry_matches_learning_list_filter(entry, 'no_activity') is True
    assert service._entry_matches_learning_list_filter(entry, 'low_progress') is True
    assert service._entry_matches_learning_list_filter(entry, 'low_grade') is True


def test_subject_filter_does_not_treat_missing_snapshot_as_known_not_enrolled():
    service = _service()
    entry = {
        'student_count': 30,
        'learning_enrolled_count': 20,
        'learning_synced_count': 20,
        'learning_active_count': 20,
        'learning_avg_progress_percent': 80.0,
        'learning_avg_grade_percent': 80.0,
        'learning_alerts': ['Chưa có dữ liệu học tập'],
        'learning_status_counts': {
            'not_enrolled': 0,
            'no_activity': 0,
            'low_progress': 0,
            'low_grade': 0,
            'sync_error': 0,
        },
    }
    assert service._entry_matches_learning_list_filter(entry, 'not_fully_enrolled') is False
""")
