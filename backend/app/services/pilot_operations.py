from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.release_candidate import ReleaseCandidateService


class PilotOperationsService:
    """Read-only pilot go-live runbook built from the release candidate gate.

    The Release Candidate gate answers "can we pilot?". This service turns that
    answer into an operator-friendly go-live runbook: entry criteria, phase
    checklist, monitoring cadence, rollback triggers, and sign-off evidence.
    It never calls external systems, enqueues jobs, recalculates analytics,
    publishes Bank releases, scans raw tracking.log, or mutates data.
    """

    safe_policy = 'read_only_pilot_operations_runbook_no_mutation'
    read_only_guarantees = [
        'Không đọc raw tracking.log trong request',
        'Không gọi Open edX/AP/OpenAI trong request',
        'Không enqueue job hoặc recalculate',
        'Không publish/rollback Bank Release',
        'Không mutate database',
        'Không kết luận vi phạm cá nhân',
    ]

    def __init__(self, db: Session):
        self.db = db

    def report(
        self,
        *,
        class_id: str | None = None,
        course_id: str | None = None,
        campus: str | None = None,
        branch: str | None = None,
        sample_limit: int = 5,
        allowed_class_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc).isoformat()
        rc = ReleaseCandidateService(self.db).report(
            class_id=class_id,
            course_id=course_id,
            campus=campus,
            branch=branch,
            sample_limit=sample_limit,
            allowed_class_ids=allowed_class_ids,
        )
        blockers = rc.get('blockers') or []
        warnings = rc.get('warnings') or []
        gates = rc.get('gates') or []
        go_no_go = str(rc.get('go_no_go') or '').upper()
        rc_status = str(rc.get('status') or '').upper()

        if blockers or go_no_go == 'HOLD' or rc_status == 'FAIL':
            status = 'HOLD'
            decision = 'NO_GO'
            summary = 'Chưa mở pilot; cần xử lý blocker trong Release Candidate gate.'
        elif warnings or rc_status == 'PASS_WITH_WARNINGS':
            status = 'PILOT_WITH_MONITORING'
            decision = 'GO_CONTROLLED_PILOT'
            summary = 'Có thể pilot có kiểm soát với monitoring và rollback criteria rõ ràng.'
        else:
            status = 'PILOT_READY'
            decision = 'GO_PILOT'
            summary = 'Đủ điều kiện chạy pilot theo các gate hiện có.'

        phases = self._phases(decision=decision, rc=rc)
        rollback_triggers = self._rollback_triggers(rc=rc, blockers=blockers, warnings=warnings)
        monitoring_cadence = self._monitoring_cadence(decision=decision, warnings=warnings)
        evidence_required = self._evidence_required()
        signoff = self._signoff(decision=decision, rc=rc)
        next_actions = self._next_actions(decision=decision, rc=rc, blockers=blockers, warnings=warnings)

        return {
            'version': settings.app_version,
            'report_type': 'pilot_operations_runbook',
            'release_candidate': f'v{settings.app_version}',
            'generated_at': generated_at,
            'status': status,
            'decision': decision,
            'summary_label': summary,
            'ready_for_pilot': bool(rc.get('ready_for_pilot')) and decision != 'NO_GO',
            'ready_for_broad_production': bool(rc.get('ready_for_broad_production')) and decision == 'GO_PILOT',
            'blocker_count': len(blockers),
            'warning_count': len(warnings),
            'filters': {
                'class_id': class_id,
                'course_id': course_id,
                'campus': campus,
                'branch': branch,
                'sample_limit': sample_limit,
            },
            'release_candidate_summary': {
                'status': rc.get('status'),
                'go_no_go': rc.get('go_no_go'),
                'ready_for_pilot': rc.get('ready_for_pilot'),
                'ready_for_broad_production': rc.get('ready_for_broad_production'),
                'blocker_count': rc.get('blocker_count'),
                'warning_count': rc.get('warning_count'),
                'summary_label': rc.get('summary_label'),
            },
            'gates': gates,
            'phases': phases,
            'monitoring_cadence': monitoring_cadence,
            'rollback_triggers': rollback_triggers,
            'evidence_required': evidence_required,
            'signoff': signoff,
            'blockers': blockers[:20],
            'warnings': warnings[:20],
            'next_actions': next_actions,
            'safe_policy': self.safe_policy,
            'read_only_guarantees': self.read_only_guarantees,
            'disclaimer': 'Pilot operations runbook là checklist vận hành UAT/pilot; vẫn cần backup, người trực, cửa sổ triển khai và rollback plan thực tế trước khi mở cho người dùng.',
        }

    @staticmethod
    def _phases(*, decision: str, rc: dict[str, Any]) -> list[dict[str, Any]]:
        blocked = decision == 'NO_GO'
        return [
            {
                'key': 'preflight',
                'title': 'Preflight trước pilot',
                'status': 'BLOCKED' if blocked else 'READY',
                'checks': [
                    'Chạy uat-build-gate.sh với STRICT=1 trên UAT thật.',
                    'Chạy pilot-release-candidate-report.sh và lưu evidence pack.',
                    'Xác nhận security/performance/readiness không còn blocker.',
                    'Chọn phạm vi pilot hẹp: campus, môn, lớp, thời gian theo dõi.',
                ],
            },
            {
                'key': 'deploy_window',
                'title': 'Cửa sổ deploy',
                'status': 'WAITING' if not blocked else 'BLOCKED',
                'checks': [
                    'Backup .env.production và ghi lại image/version đang chạy.',
                    'Deploy đúng zip/root của bản hiện tại.',
                    'Force recreate backend/frontend/worker/beat.',
                    'Kiểm tra /api/health/build trả đúng APP_VERSION.',
                ],
            },
            {
                'key': 'warmup',
                'title': 'Warm-up sau deploy',
                'status': 'WAITING' if not blocked else 'BLOCKED',
                'checks': [
                    'Chờ ít nhất 2 chu kỳ ingest để post-ingest orchestrator tạo job.',
                    'Kiểm tra /jobs không có job analytics fail lặp lại.',
                    'Kiểm tra /analytics/learning có SLA và mapping Course/Lớp rõ.',
                    'Kiểm tra một lớp pilot bằng Class Doctor trước khi thông báo người dùng.',
                ],
            },
            {
                'key': 'pilot_monitoring',
                'title': 'Theo dõi pilot',
                'status': 'READY' if decision != 'NO_GO' else 'BLOCKED',
                'checks': [
                    'Theo dõi security/performance/readiness/release-candidate mỗi 30 phút trong 2 giờ đầu.',
                    'Theo dõi ingest latency và snapshot latency.',
                    'Theo dõi lớp có roster nhưng thiếu snapshot hoặc mapping ambiguous.',
                    'Không dùng nhãn kết luận cứng cho sinh viên; chỉ dùng tín hiệu mềm.',
                ],
            },
            {
                'key': 'signoff_or_rollback',
                'title': 'Ký duyệt hoặc rollback',
                'status': 'WAITING',
                'checks': [
                    'Ký duyệt nếu các gate vẫn ổn sau cửa sổ pilot.',
                    'Rollback nếu xuất hiện blocker security/performance hoặc lỗi data identity/mapping diện rộng.',
                    'Lưu evidence pack sau pilot để đối chiếu.',
                ],
            },
        ]

    @staticmethod
    def _monitoring_cadence(*, decision: str, warnings: list[dict[str, Any]]) -> list[dict[str, str]]:
        interval = '15 phút' if warnings else '30 phút'
        if decision == 'NO_GO':
            interval = 'Sau khi xử lý blocker'
        return [
            {'window': '0-2 giờ đầu', 'frequency': interval, 'check': 'release-candidate, security, performance, SLA analytics, jobs failed'},
            {'window': 'Trong ngày pilot', 'frequency': 'Mỗi 2 giờ', 'check': 'class doctor cho lớp pilot, mapping report, evidence pack'},
            {'window': 'Cuối ngày pilot', 'frequency': 'Một lần', 'check': 'xuất pilot-release-candidate-report.sh và evidence pack'},
        ]

    @staticmethod
    def _rollback_triggers(*, rc: dict[str, Any], blockers: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        triggers = [
            {
                'code': 'SECURITY_BLOCKER',
                'severity': 'BLOCKER',
                'condition': 'Security readiness chuyển sang BLOCKED hoặc phát hiện secret/default credential production.',
                'action': 'Dừng mở rộng pilot, khôi phục cấu hình an toàn, chạy lại security-readiness-report.sh.',
            },
            {
                'code': 'PERFORMANCE_BLOCKER',
                'severity': 'BLOCKER',
                'condition': 'Performance readiness BLOCKED, job queue tăng liên tục, hoặc failed analytics jobs lặp lại.',
                'action': 'Giảm phạm vi pilot, giảm max jobs/run, kiểm tra worker/DB, rollback nếu không ổn định.',
            },
            {
                'code': 'IDENTITY_MAPPING_RISK',
                'severity': 'BLOCKER',
                'condition': 'RollNumber identity/mapping có duplicate hoặc legacy AP username ảnh hưởng lớp pilot.',
                'action': 'Dừng enrollment/sync diện rộng, chạy rollnumber identity report và cleanup UAT nếu được phép.',
            },
            {
                'code': 'ANALYTICS_MAPPING_GAP',
                'severity': 'WARNING',
                'condition': 'Course có tracking events nhưng không resolve được class hoặc nhiều class ambiguous.',
                'action': 'Giới hạn pilot ở lớp mapping READY; xử lý mapping trước khi mở rộng.',
            },
        ]
        for item in blockers[:5]:
            triggers.append({
                'code': f"RC_{item.get('code') or item.get('source') or 'BLOCKER'}",
                'severity': 'BLOCKER',
                'condition': item.get('message') or 'Release Candidate còn blocker.',
                'action': item.get('action') or 'Xử lý blocker trong release-candidate report trước khi pilot.',
            })
        return triggers

    @staticmethod
    def _evidence_required() -> list[str]:
        return [
            'BUILD_GATE_SUMMARY.md từ scripts/uat-build-gate.sh',
            'PILOT_RELEASE_CANDIDATE_SUMMARY.md từ scripts/pilot-release-candidate-report.sh',
            'security-readiness.json và performance-readiness.json',
            'evidence-pack.json và optional class-doctor.json cho lớp pilot',
            'Log deploy gồm zip/root/version/image tag và thời điểm force recreate',
        ]

    @staticmethod
    def _signoff(*, decision: str, rc: dict[str, Any]) -> dict[str, Any]:
        return {
            'required_roles': ['SYSTEM_ADMIN', 'CAMPUS_MANAGER đúng campus pilot', 'Người vận hành UAT'],
            'minimum_decision': 'GO_CONTROLLED_PILOT',
            'current_decision': decision,
            'can_signoff_pilot': decision in {'GO_CONTROLLED_PILOT', 'GO_PILOT'},
            'can_signoff_broad_production': bool(rc.get('ready_for_broad_production')) and decision == 'GO_PILOT',
        }

    @staticmethod
    def _next_actions(*, decision: str, rc: dict[str, Any], blockers: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> list[str]:
        if decision == 'NO_GO':
            actions = ['Xử lý blocker trong release-candidate gate trước khi mở pilot.']
            actions.extend([str(item.get('action') or item.get('message')) for item in blockers[:4] if item.get('action') or item.get('message')])
            return actions[:6]
        if warnings:
            actions = ['Chạy pilot hẹp có monitoring; không mở rộng toàn campus ngay.']
            actions.extend([str(item.get('action') or item.get('message')) for item in warnings[:4] if item.get('action') or item.get('message')])
            actions.append('Xuất evidence pack sau 2 giờ đầu để so sánh trước/sau deploy.')
            return actions[:6]
        return [
            'Chạy pilot với phạm vi đã chọn và lưu evidence pack trước/sau deploy.',
            'Theo dõi SLA analytics, security và performance trong 2 giờ đầu.',
            'Chỉ mở rộng production sau khi pilot không phát sinh blocker mới.',
        ]
