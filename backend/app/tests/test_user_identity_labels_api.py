from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.identity import AIUserProfile


def _db():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    AIUserProfile.__table__.create(engine)
    return engine, Session(engine)


def test_bulk_identity_labels_return_username_without_email_and_ignore_missing_ids():
    from app.api.routes.users import user_identity_labels

    engine, db = _db()
    db.add(AIUserProfile(
        user_id='14414',
        username='thaitx3',
        display_name='Thái Trần',
        email='thai@example.edu.vn',
    ))
    db.commit()

    result = user_identity_labels(
        user_ids=['14414', '14414', 'missing'],
        db=db,
        user=SimpleNamespace(user_id='viewer'),
    )

    assert result == {
        'items': [{
            'user_id': '14414',
            'username': 'thaitx3',
            'display_name': 'Thái Trần',
        }],
    }
    assert 'email' not in result['items'][0]
    db.close()
    engine.dispose()


def test_bulk_identity_labels_reject_more_than_two_hundred_ids():
    from app.api.routes.users import user_identity_labels

    engine, db = _db()
    with pytest.raises(HTTPException) as caught:
        user_identity_labels(
            user_ids=[str(index) for index in range(201)],
            db=db,
            user=SimpleNamespace(user_id='viewer'),
        )
    assert caught.value.status_code == 422
    db.close()
    engine.dispose()
