from __future__ import annotations

import ast
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'backend/app/services/academic_subject_overview_performance.py'
ACADEMIC_SERVICE_SOURCE = ROOT / 'backend/app/services/academic_service.py'


@dataclass(frozen=True)
class _Field:
    owner: str
    name: str

    def in_(self, values):
        return ('in', self, tuple(values))

    def __eq__(self, other):
        return ('eq', self.owner, self.name, getattr(other, 'owner', None), getattr(other, 'name', None))


class _Count:
    pass


class _Func:
    @staticmethod
    def count(_field):
        return _Count()


class _OverviewMode:
    @staticmethod
    def get():
        return True


class _ClassStudent:
    id = _Field('class_student', 'id')
    class_id = _Field('class_student', 'class_id')
    student_id = _Field('class_student', 'student_id')


class _Snapshot:
    class_id = _Field('snapshot', 'class_id')
    student_id = _Field('snapshot', 'student_id')
    openedx_course_id = _Field('snapshot', 'openedx_course_id')
    enrollment_status = _Field('snapshot', 'enrollment_status')
    progress_percent = _Field('snapshot', 'progress_percent')
    grade_percent = _Field('snapshot', 'grade_percent')
    completed_blocks = _Field('snapshot', 'completed_blocks')
    last_activity_at = _Field('snapshot', 'last_activity_at')
    learning_synced_at = _Field('snapshot', 'learning_synced_at')
    last_synced_at = _Field('snapshot', 'last_synced_at')


class _AcademicClass:
    id = _Field('academic_class', 'id')


class _Query:
    def __init__(self, columns, roster, snapshots):
        self.columns = columns
        self.roster = roster
        self.snapshots = snapshots
        self.current_roster_only = False

    def filter(self, *_args):
        return self

    def group_by(self, *_args):
        return self

    def join(self, target, *_args):
        required_identity = {
            ('eq', 'class_student', 'class_id', 'snapshot', 'class_id'),
            ('eq', 'class_student', 'student_id', 'snapshot', 'student_id'),
        }
        conditions = set(_args[0]) if _args and isinstance(_args[0], tuple) else set()
        if target is _ClassStudent and conditions == required_identity:
            self.current_roster_only = True
        return self

    def all(self):
        if self.columns and getattr(self.columns[0], 'owner', None) == 'class_student':
            counts: dict[str, int] = {}
            for class_id, _student_id in self.roster:
                counts[class_id] = counts.get(class_id, 0) + 1
            return sorted(counts.items())

        rows = list(self.snapshots)
        if self.current_roster_only:
            rows = [row for row in rows if (row['class_id'], row['student_id']) in self.roster]
        if self.columns and self.columns[0] is _Snapshot:
            return [SimpleNamespace(**row) for row in rows]
        if self.columns and self.columns[0] is _AcademicClass:
            return [SimpleNamespace(id='class-1')]
        return [tuple(row[column.name] for column in self.columns) for row in rows]


class _Db:
    def __init__(self):
        self.roster = {('class-1', 'student-1'), ('class-1', 'student-2')}
        self.snapshots = [
            {
                'class_id': 'class-1', 'student_id': 'student-1', 'openedx_course_id': 'course-v1:FPL+ACC1061+FA26',
                'enrollment_status': 'enrolled', 'progress_percent': 10.0, 'grade_percent': None,
                'completed_blocks': 1, 'last_activity_at': None, 'learning_synced_at': None, 'last_synced_at': None,
            },
            {
                'class_id': 'class-1', 'student_id': 'student-2', 'openedx_course_id': 'course-v1:FPL+ACC1061+FA26',
                'enrollment_status': 'enrolled', 'progress_percent': 0.0, 'grade_percent': None,
                'completed_blocks': 0, 'last_activity_at': None, 'learning_synced_at': None, 'last_synced_at': None,
            },
            {
                'class_id': 'class-1', 'student_id': 'student-removed', 'openedx_course_id': 'course-v1:FPL+ACC1061+FA26',
                'enrollment_status': 'enrolled', 'progress_percent': 50.0, 'grade_percent': None,
                'completed_blocks': 3, 'last_activity_at': None, 'learning_synced_at': None, 'last_synced_at': None,
            },
        ]

    def query(self, *columns):
        return _Query(columns, self.roster, self.snapshots)


def _load_fast_summary_function():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    selected = [
        node for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == '__future__'
        or isinstance(node, ast.FunctionDef) and node.name in {'_percent', '_learning_summary_by_class_ids_fast'}
    ]
    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        'Any': object,
        'AcademicService': object,
        'AcademicClassStudent': _ClassStudent,
        'AcademicStudentLearningSnapshot': _Snapshot,
        '_OVERVIEW_MODE': _OverviewMode(),
        '_ORIGINAL_LEARNING_SUMMARY_BY_CLASS_IDS': None,
        'and_': lambda *conditions: conditions,
        'func': _Func(),
    }
    exec(compile(module, str(SOURCE), 'exec'), namespace)
    return namespace['_learning_summary_by_class_ids_fast']


def _load_full_summary_function():
    tree = ast.parse(ACADEMIC_SERVICE_SOURCE.read_text(encoding='utf-8'))
    service_class = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == 'AcademicService'
    )
    function = next(
        node for node in service_class.body
        if isinstance(node, ast.FunctionDef) and node.name == '_learning_summary_by_class_ids'
    )
    future = next(
        node for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == '__future__'
    )
    module = ast.Module(body=[future, function], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        'AcademicClass': _AcademicClass,
        'AcademicClassStudent': _ClassStudent,
        'AcademicStudentLearningSnapshot': _Snapshot,
        'Any': object,
        'and_': lambda *conditions: conditions,
        'func': _Func(),
    }
    exec(compile(module, str(ACADEMIC_SERVICE_SOURCE), 'exec'), namespace)
    return namespace['_learning_summary_by_class_ids']


class AcademicEnrollmentCountCurrentRosterTest(unittest.TestCase):
    def test_removed_student_snapshot_does_not_inflate_subject_enrollment(self):
        service = SimpleNamespace(
            db=_Db(),
            _learning_alerts_from_summary=lambda **_kwargs: [],
        )

        result = _load_fast_summary_function()(
            service,
            ['class-1'],
            {'class-1': 'course-v1:FPL+ACC1061+FA26'},
        )['class-1']

        self.assertEqual(result['learning_enrolled_count'], 2)
        self.assertEqual(result['learning_synced_count'], 2)
        self.assertEqual(result['learning_active_count'], 1)
        self.assertEqual(result['learning_avg_progress_percent'], 5.0)

    def test_class_detail_summary_uses_the_same_current_roster_boundary(self):
        service = SimpleNamespace(
            db=_Db(),
            _snapshot_progress_percent=lambda snapshot: snapshot.progress_percent,
            _snapshot_grade_percent=lambda snapshot: snapshot.grade_percent,
            _snapshot_has_learning_activity=lambda snapshot: bool(
                str(snapshot.enrollment_status).lower() == 'enrolled'
                and (float(snapshot.progress_percent or 0) > 0 or int(snapshot.completed_blocks or 0) > 0)
            ),
            _component_summary_from_snapshots=lambda *_args: [],
            _learning_issue_counts_from_snapshots=lambda _snapshots: {},
            _learning_alerts_from_summary=lambda **_kwargs: [],
        )

        result = _load_full_summary_function()(
            service,
            ['class-1'],
            {'class-1': 'course-v1:FPL+ACC1061+FA26'},
        )['class-1']

        self.assertEqual(result['learning_enrolled_count'], 2)
        self.assertEqual(result['learning_synced_count'], 2)
        self.assertEqual(result['learning_active_count'], 1)
        self.assertEqual(result['learning_avg_progress_percent'], 5.0)


if __name__ == '__main__':
    unittest.main()
