import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app.core.db import SessionLocal
from app.core.metrics import HTTP_DURATION, HTTP_REQUESTS
from app.modules.arch.router import router as arch_router
from app.modules.assess.router import admin_router as assess_admin_router
from app.modules.assess.router import router as assess_router
from app.modules.auth.router import router as auth_router
from app.modules.auth.service import ensure_bootstrap_users
from app.modules.courses.router import admin_router as courses_admin_router
from app.modules.courses.router import review_router as fragments_review_router
from app.modules.courses.router import router as courses_router
from app.modules.generation.router import proposals_router
from app.modules.generation.router import router as generation_router
from app.modules.library.router import admin_router as sources_admin_router
from app.modules.library.router import router as library_router
from app.modules.mentor.router import router as mentor_router
from app.modules.paths.router import preview_router
from app.modules.paths.router import router as paths_router
from app.modules.practice.router import admin_router as tasks_admin_router
from app.modules.practice.router import router as practice_router
from app.modules.quiz.router import admin_router as quiz_admin_router
from app.modules.quiz.router import router as quiz_router
from app.modules.review.router import admin_router as review_admin_router
from app.modules.review.router import router as review_router
from app.modules.system.router import router as system_router
from app.modules.users.router import router as users_router
from app.modules.workshop.router import router as workshop_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        ensure_bootstrap_users(db)
    yield


app = FastAPI(title="Развилка API", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(system_router)
app.include_router(workshop_router)
app.include_router(library_router)
app.include_router(courses_router)
app.include_router(practice_router)
app.include_router(quiz_router)
app.include_router(mentor_router)
app.include_router(proposals_router)
app.include_router(review_router)
app.include_router(assess_router)
app.include_router(arch_router)
app.include_router(paths_router)
app.include_router(preview_router)
# Мастерская: каждый роутер закрыт require_admin на уровне маршрутов
app.include_router(sources_admin_router)
app.include_router(courses_admin_router)
app.include_router(fragments_review_router)
app.include_router(users_router)
app.include_router(tasks_admin_router)
app.include_router(quiz_admin_router)
app.include_router(generation_router)
app.include_router(review_admin_router)
app.include_router(assess_admin_router)


@app.middleware("http")
async def record_metrics(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    # Шаблон маршрута (/api/items/{id}), а не реальный путь — иначе метрик будет по одной на каждый id.
    route = getattr(request.scope.get("route"), "path", "unmatched")
    if route != "/metrics":
        HTTP_REQUESTS.labels(request.method, route, str(response.status_code)).inc()
        HTTP_DURATION.labels(request.method, route).observe(time.perf_counter() - started)
    return response


@app.get("/metrics", include_in_schema=False)
def metrics():
    # Наружу не проксируется (nginx пропускает только /api): метрики читает Prometheus по внутренней сети.
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
