from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAGE = ROOT / 'frontend' / 'app' / 'analytics' / 'learning' / 'page.tsx'
CSS = ROOT / 'frontend' / 'app' / 'globals.css'


def test_learning_page_is_result_first_hierarchy_flow():
    text = PAGE.read_text(encoding='utf-8')
    assert 'Phân tích hành vi học' in text
    assert 'Học kỳ' in text
    assert 'Cơ sở' in text
    assert 'Môn' in text
    assert 'Lớp' in text
    assert 'Kết quả' in text
    assert 'getAcademicTerms' in text
    assert 'getAcademicCampuses' in text
    assert 'getAcademicTeacherSubjects' in text
    assert 'getAcademicSubjectClasses' not in text
    assert 'getAnalyticsClassLearningBehavior' in text
    assert 'getAnalyticsStudentLearningBehaviorDetail' in text


def test_learning_page_removes_ops_noise_from_primary_view():
    text = PAGE.read_text(encoding='utf-8')
    forbidden = [
        'Pilot acceptance',
        'Production readiness',
        'Rollout',
        'Monitoring',
        'Backfill học online',
        'Xuất CSV',
        'Tải lại',
        'Lớp cần chú ý',
        'Deadline cần chú ý',
    ]
    for item in forbidden:
        assert item not in text


def test_result_click_opens_reason_detail_not_reason_columns():
    text = PAGE.read_text(encoding='utf-8')
    assert 'Lý do ra kết quả' in text
    assert 'openReason(row)' in text
    assert 'aria-label={`Xem lý do kết quả của ${row.username}`}' in text
    assert '<th>Dấu hiệu chính</th>' not in text
    assert '<th>Hành động</th>' not in text
    assert 'Lý do chính' in text


def test_css_has_drawer_and_result_flow_styles():
    text = CSS.read_text(encoding='utf-8')
    assert 'analytics-result-drawer-backdrop' in text
    assert '.analytics-result-drawer-backdrop' in text
    assert '.analytics-learning-flow-filters' in text
    assert '.analytics-result-button:focus-visible' in text
