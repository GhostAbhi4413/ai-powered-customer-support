"""ASGI application entry point."""

import sqlite3
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.support import router
from backend.app.db.database import connection, initialize
from backend.app.models.support import Health
from backend.app.services.support import SupportError, SupportService

from backend.app.config import get_settings
from backend.app.api.agent import router as agent_router
from backend.app.ai.gemini import GeminiModel


def create_app(settings=None, *, clock=None, model_factory=GeminiModel) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app):
        initialize(settings.database_path)
        yield

    app = FastAPI(title=settings.name, lifespan=lifespan)
    app.state.support = SupportService(settings, clock=clock)
    app.state.settings = settings
    app.state.model_factory = model_factory
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_credentials=False, allow_methods=['GET','PATCH','POST'],
                       allow_headers=['Content-Type'])

    @app.exception_handler(SupportError)
    async def support_error(request: Request, exc: SupportError):
        return JSONResponse(status_code=exc.status, content={'detail': exc.message})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={'detail': 'Invalid request parameters or body'})

    @app.exception_handler(sqlite3.Error)
    async def database_error(request: Request, exc: sqlite3.Error):
        return JSONResponse(status_code=503, content={'detail': 'Database operation unavailable'})

    @app.get('/health', response_model=Health, tags=['health'])
    def health():
        with connection(settings.database_path, readonly=True) as db:
            db.execute('SELECT 1').fetchone()
        return {'status': 'ok'}

    app.include_router(router)
    app.include_router(agent_router)
    return app


app = create_app()
