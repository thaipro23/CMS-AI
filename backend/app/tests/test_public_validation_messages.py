from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app.core.errors import validation_exception_handler
from app.schemas.rbac import RoleAssignmentCreate


def test_custom_validation_error_returns_json_422_without_submitted_identity():
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    @app.post('/assign')
    def assign(payload: RoleAssignmentCreate):
        return payload

    with TestClient(app) as client:
        response = client.post('/assign', headers={'X-Request-ID': 'validation-test'}, json={
            'user_id': 'example-account', 'email': 'example@example.test',
            'role_code': 'invalid', 'scope_type': 'SYSTEM', 'scope_id': '*',
        })
    assert response.status_code == 422
    error = response.json()['error']
    assert error['code'] == 'VALIDATION_ERROR'
    assert error['request_id'] == 'validation-test'
    assert error['details'][0]['loc'] == ['body', 'role_code']
    assert error['details'][0]['msg'].endswith('Vai trò không hợp lệ để cấp quyền mới.')
    assert 'input' not in error['details'][0]
    assert 'example-account' not in response.text
    assert 'example@example.test' not in response.text
