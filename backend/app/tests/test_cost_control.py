from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session import Base
from app.models import course, question, cost, job  # noqa: F401
from app.services.cost_control import CostControlService


def make_session():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_estimate_generation_cost_has_safety_factor():
    db = make_session()
    try:
        svc = CostControlService(db)
        est = svc.estimate_generation_cost('course-v1:TEST+AI+2026', 50, 30000)
        assert est.input_tokens > 30000
        assert est.output_tokens == 50 * 320
        assert est.cost_usd > 0
        assert est.quota_ok is True
    finally:
        db.close()
