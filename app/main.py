from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from app.agent import OpenAIAgentClient
from app.config import Settings, get_settings
from app.errors import AgentServiceError, SessionNotFoundError
from app.models import (
    CreateWorkSessionRequest,
    FinalizeSessionRequest,
    FinalizeSessionResponse,
    HealthResponse,
    SendMessageRequest,
    SendMessageResponse,
    WorkSessionResponse,
)
from app.repositories import FirestoreWorkSessionRepository, InMemoryWorkSessionRepository
from app.service import WorkPlanningService


def create_app(
    settings: Settings | None = None,
    repository=None,
    agent=None,
) -> FastAPI:
    settings = settings or get_settings()
    service = (
        WorkPlanningService(repository, agent)
        if repository is not None and agent is not None
        else None
    )

    application = FastAPI(
        title="Tomorrow Desk API",
        version="0.1.0",
        description="업무 목록을 Agent와 함께 내일의 계획으로 정리하는 API",
    )
    application.state.settings = settings
    application.state.repository = repository
    application.state.agent = agent
    application.state.service = service

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @application.exception_handler(SessionNotFoundError)
    async def session_not_found_handler(_request: Request, _exc: SessionNotFoundError):
        return _error_response(status.HTTP_404_NOT_FOUND, "업무 세션을 찾을 수 없습니다.")

    @application.exception_handler(AgentServiceError)
    async def agent_error_handler(_request: Request, exc: AgentServiceError):
        return _error_response(status.HTTP_502_BAD_GATEWAY, str(exc))

    @application.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            environment=settings.app_env,
            storage=settings.storage_backend,
            openai_configured=bool(settings.openai_api_key),
            timestamp=datetime.now(UTC),
        )

    @application.post(
        "/work-sessions",
        response_model=WorkSessionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_work_session(payload: CreateWorkSessionRequest) -> WorkSessionResponse:
        if not payload.completed_tasks and not payload.upcoming_tasks:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="업무를 한 가지 이상 입력해 주세요.",
            )
        return await _get_service(application).create_session(payload)

    @application.post(
        "/work-sessions/{session_id}/messages",
        response_model=SendMessageResponse,
    )
    async def send_message(session_id: str, payload: SendMessageRequest) -> SendMessageResponse:
        return await _get_service(application).send_message(session_id, payload)

    @application.post(
        "/work-sessions/{session_id}/finalize",
        response_model=FinalizeSessionResponse,
    )
    async def finalize_session(
        session_id: str,
        payload: FinalizeSessionRequest,
    ) -> FinalizeSessionResponse:
        return await _get_service(application).finalize_session(session_id, payload)

    return application


def _error_response(status_code: int, message: str):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status_code, content={"detail": message})


def _get_service(application: FastAPI) -> WorkPlanningService:
    if application.state.service is not None:
        return application.state.service

    settings = application.state.settings
    repository = (
        InMemoryWorkSessionRepository()
        if settings.storage_backend == "memory"
        else FirestoreWorkSessionRepository(
            settings.firestore_project_id,
            settings.firestore_collection,
        )
    )
    agent = OpenAIAgentClient(settings)
    application.state.repository = repository
    application.state.agent = agent
    application.state.service = WorkPlanningService(repository, agent)
    return application.state.service


app = create_app()
