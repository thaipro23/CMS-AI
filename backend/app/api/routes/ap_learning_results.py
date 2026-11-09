from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.core.ap_analytics_auth import APAnalyticsClient, get_ap_analytics_client
from app.db.session import get_db
from app.schemas.ap_learning_results import APClassResults, APStudentResult
from app.services.ap_learning_results import APLearningResultsService

class NoStoreRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def no_store_handler(request):
            try:
                response = await handler(request)
            except HTTPException as exc:
                exc.headers = {**(exc.headers or {}), 'Cache-Control': 'no-store'}
                raise
            except RequestValidationError as exc:
                response = await request_validation_exception_handler(request, exc)
            response.headers['Cache-Control'] = 'no-store'
            return response

        return no_store_handler


router = APIRouter(route_class=NoStoreRoute)


def ap_class_scope(
    response: Response,
    ap_class_id: str,
    branch: Literal['poly', 'ptcd'],
    campus: str = Query(min_length=1, max_length=64),
    ap_term_id: str = Query(min_length=1, max_length=64),
    subject_code: str = Query(min_length=1, max_length=64),
    ap_block_id: str | None = Query(default=None, min_length=1, max_length=64),
    client: APAnalyticsClient = Depends(get_ap_analytics_client),
):
    client.assert_scope(branch, campus)
    response.headers['Cache-Control'] = 'no-store'
    return dict(ap_class_id=ap_class_id, branch=branch, campus=campus,
                ap_term_id=ap_term_id, subject_code=subject_code, ap_block_id=ap_block_id)


@router.get('/classes/{ap_class_id}/learning-results', response_model=APClassResults)
def class_learning_results(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    scope: dict = Depends(ap_class_scope),
    db: Session = Depends(get_db),
):
    return APLearningResultsService(db).class_results(limit=limit, offset=offset, **scope)


@router.get('/classes/{ap_class_id}/students/{student_code}/learning-results', response_model=APStudentResult)
def student_learning_result(
    student_code: str,
    scope: dict = Depends(ap_class_scope),
    db: Session = Depends(get_db),
):
    return APLearningResultsService(db).student_result(student_code=student_code, **scope)
