from fastapi import APIRouter
from app.api.routes import health, cost, courses, generation, questions, jobs, auth, analytics, publish, users, settings, libraries, audit, concepts, question_bank_v2, rbac, academic

api_router = APIRouter()
api_router.include_router(health.router, tags=['health'])
api_router.include_router(auth.router, prefix='/auth', tags=['auth'])
api_router.include_router(analytics.router, prefix='/analytics', tags=['analytics'])
api_router.include_router(cost.router, prefix='/cost', tags=['cost'])
api_router.include_router(courses.router, prefix='/courses', tags=['courses'])
api_router.include_router(generation.router, prefix='/questions', tags=['generation'])
api_router.include_router(questions.router, prefix='/question-bank', tags=['question-bank'])
api_router.include_router(question_bank_v2.router, prefix='/question-bank-v2', tags=['question-bank-v2'])
api_router.include_router(publish.router, prefix='/publish', tags=['publish'])
api_router.include_router(jobs.router, prefix='/jobs', tags=['jobs'])
api_router.include_router(users.router, prefix='/users', tags=['users'])
api_router.include_router(rbac.router, prefix='/rbac', tags=['rbac'])
api_router.include_router(academic.router, prefix='/academic', tags=['academic'])

api_router.include_router(settings.router, prefix='/settings', tags=['settings'])

api_router.include_router(libraries.router, prefix='/libraries', tags=['libraries'])

api_router.include_router(audit.router, prefix='/audit', tags=['audit'])
api_router.include_router(concepts.router, tags=['concepts'])
