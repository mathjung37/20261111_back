from __future__ import annotations

from app.agent import OpenAIAgentClient
from app.models import (
    CreateWorkSessionRequest,
    FinalizeSessionRequest,
    FinalizeSessionResponse,
    SendMessageRequest,
    SendMessageResponse,
    WorkSessionResponse,
)
from app.repositories import WorkSessionRepository


class WorkPlanningService:
    def __init__(
        self,
        repository: WorkSessionRepository,
        agent: OpenAIAgentClient,
    ) -> None:
        self.repository = repository
        self.agent = agent

    async def create_session(self, request: CreateWorkSessionRequest) -> WorkSessionResponse:
        result = await self.agent.create_planning_session(
            request.completed_tasks,
            request.upcoming_tasks,
        )
        plan_data = [item.model_dump() for item in result.plan]
        await self.repository.create(
            result.session_id,
            {
                "openai_session_id": result.session_id,
                "completed_tasks": request.completed_tasks,
                "upcoming_tasks": request.upcoming_tasks,
                "plan": plan_data,
                "skill_id": self.agent.settings.openai_skill_id,
            },
        )
        await self.repository.add_message(result.session_id, "assistant", result.assistant_message)
        return WorkSessionResponse(
            session_id=result.session_id,
            assistant_message=result.assistant_message,
            plan=result.plan,
        )

    async def send_message(
        self,
        session_id: str,
        request: SendMessageRequest,
    ) -> SendMessageResponse:
        session = await self.repository.get(session_id)
        await self.repository.add_message(session_id, "user", request.message)
        result = await self.agent.continue_planning_session(
            session["openai_session_id"],
            request.message,
            request.plan,
        )
        await self.repository.add_message(session_id, "assistant", result.assistant_message)
        await self.repository.update_plan(
            session_id,
            [item.model_dump() for item in result.plan],
        )
        return SendMessageResponse(
            assistant_message=result.assistant_message,
            plan=result.plan,
        )

    async def finalize_session(
        self,
        session_id: str,
        request: FinalizeSessionRequest,
    ) -> FinalizeSessionResponse:
        await self.repository.get(session_id)
        result = await self.agent.finalize_plan(request.plan)
        submitted_plan = [item.model_dump() for item in request.plan]
        final_plan = [item.model_dump() for item in result.plan]
        await self.repository.finalize(
            session_id,
            submitted_plan,
            final_plan,
            result.session_id,
        )
        return FinalizeSessionResponse(saved=True, plan_count=len(final_plan))
