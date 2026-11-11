from fastapi.testclient import TestClient

from app.agent import AgentTurnResult
from app.config import Settings
from app.main import create_app
from app.models import PlanItem
from app.repositories import InMemoryWorkSessionRepository


class FakeAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def create_planning_session(self, completed_tasks, upcoming_tasks):
        return AgentTurnResult(
            session_id="session-test",
            assistant_message="내일의 초안을 만들었어요.",
            plan=[PlanItem(id="plan-1", title=upcoming_tasks[0], completed=False)],
        )

    async def continue_planning_session(self, session_id, message, current_plan):
        return AgentTurnResult(
            session_id=session_id,
            assistant_message="말씀하신 조건을 반영했어요.",
            plan=current_plan,
        )

    async def finalize_plan(self, plan):
        return AgentTurnResult(
            session_id="final-agent-session",
            assistant_message="최종 계획을 정리했어요.",
            plan=plan,
        )


def make_client():
    settings = Settings(
        storage_backend="memory",
        openai_api_key="test-key",
        allowed_origins="http://localhost:4173",
    )
    repository = InMemoryWorkSessionRepository()
    app = create_app(settings, repository, FakeAgent(settings))
    return TestClient(app), repository


def test_health_does_not_expose_secrets():
    client, _ = make_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["openaiConfigured"] is True
    assert "test-key" not in response.text


def test_create_chat_and_finalize_work_session():
    client, repository = make_client()

    created = client.post(
        "/work-sessions",
        json={"completedTasks": ["기획 완료"], "upcomingTasks": ["API 구현"]},
    )
    assert created.status_code == 201
    assert created.json()["sessionId"] == "session-test"
    assert created.json()["plan"][0]["title"] == "API 구현"

    chatted = client.post(
        "/work-sessions/session-test/messages",
        json={"message": "오후에 진행할게요.", "plan": created.json()["plan"]},
    )
    assert chatted.status_code == 200
    assert chatted.json()["assistantMessage"] == "말씀하신 조건을 반영했어요."

    finalized = client.post(
        "/work-sessions/session-test/finalize",
        json={"plan": chatted.json()["plan"]},
    )
    assert finalized.status_code == 200
    assert finalized.json() == {"saved": True, "planCount": 1}
    assert repository.sessions["session-test"]["status"] == "finalized"
    assert repository.sessions["session-test"]["submitted_plan"][0]["title"] == "API 구현"


def test_rejects_empty_work_list():
    client, _ = make_client()
    response = client.post("/work-sessions", json={"completedTasks": [], "upcomingTasks": []})
    assert response.status_code == 422


def test_unknown_session_returns_404():
    client, _ = make_client()
    response = client.post(
        "/work-sessions/missing/messages",
        json={"message": "테스트", "plan": []},
    )
    assert response.status_code == 404
