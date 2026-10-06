"""Recalculate cached overall grades from equal-weight Quiz/Final assessments."""
from alembic import op
from sqlalchemy import select, update, bindparam

from app.models.academic import AcademicStudentLearningSnapshot
from app.services.academic_service import AcademicService

revision = '0073_assessment_average_grade'
down_revision = '0072_quiz_tracking_integrity'
branch_labels = None
depends_on = None


def _recalculate(*, restore_cms_grade: bool = False):
    bind = op.get_bind()
    table = AcademicStudentLearningSnapshot.__table__
    statement = update(table).where(table.c.id == bindparam('_snapshot_id')).values(
        grade_percent=bindparam('_grade_percent'),
        updated_at=table.c.updated_at,
    )
    service = AcademicService(None)
    last_id = None
    while True:
        query = select(table.c.id, table.c.raw_json).order_by(table.c.id).limit(500)
        if last_id is not None:
            query = query.where(table.c.id > last_id)
        rows = bind.execute(query).all()
        if not rows:
            break
        values = []
        for row in rows:
            snapshot = AcademicStudentLearningSnapshot(raw_json=row.raw_json)
            if restore_cms_grade:
                payload = service._payload_from_snapshot(snapshot)
                grade = payload.get('grade') if isinstance(payload.get('grade'), dict) else {}
                percent = service._float_or_none(payload.get('grade_percent', grade.get('percent')))
            else:
                percent = service._snapshot_grade_percent(snapshot)
            values.append({'_snapshot_id': row.id, '_grade_percent': percent})
        bind.execute(statement, values)
        last_id = rows[-1].id


def upgrade():
    # Only the cached grade changes; completion, raw CMS payloads and original
    # sync timestamps remain evidence of the actual Open edX read.
    _recalculate()


def downgrade():
    _recalculate(restore_cms_grade=True)
