from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings
from app.errors import AgentServiceError
from app.models import PlanItem

PLAN_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "assistantMessage": {"type": "string"},
        "plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["assistantMessage", "plan"],
    "additionalProperties": False,
}


CHAT_AGENT_INSTRUCTIONS = """
당신은 사용자의 업무 목록을 바탕으로 내일과 향후 계획을 함께 만드는 한국어 대화 Agent입니다.
환경에 설치된 tomorrow-work-planner Skill을 반드시 읽고 그 지침을 따르세요.
사용자의 제약과 우선순위를 대화로 파악하고, 매 응답마다 현재의 내일 할 일 초안을 함께 반환하세요.
업무를 임의로 완료 처리하거나 사용자가 말하지 않은 마감일을 만들지 마세요.
assistantMessage는 자연스러운 한국어 대화 한 번으로, plan은 현재 합의된 내일 할 일만 반환하세요.
""".strip()


FINAL_AGENT_INSTRUCTIONS = """
당신은 확정 직전의 업무 계획을 저장 가능한 최종 목록으로 정리하는 한국어 업무 정리 Agent입니다.
환경에 설치된 tomorrow-work-planner Skill을 반드시 읽고 그 지침을 따르세요.
사용자가 확정한 업무를 누락하거나 새로운 업무를 만들지 마세요. 중복과 표현만 정리하세요.
assistantMessage에는 정리 결과를 한 문장으로 설명하고, plan에는 확정할 내일 할 일을 반환하세요.
""".strip()


@dataclass(slots=True)
class AgentTurnResult:
    session_id: str
    assistant_message: str
    plan: list[PlanItem]


class OpenAIAgentClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    def _headers(self) -> dict[str, str]:
        if not self.settings.openai_api_key:
            raise AgentServiceError("OPENAI_API_KEY가 설정되지 않았습니다.")
        return {
            "Authorization": f"Bearer {self.settings.openai_api_key.get_secret_value()}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "agents=v1",
        }

    def _new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.openai_base_url.rstrip("/"),
            headers=self._headers(),
            timeout=httpx.Timeout(self.settings.openai_request_timeout_seconds),
        )

    def _session_payload(self, prompt: str, instructions: str) -> dict[str, Any]:
        skill_reference: dict[str, str] = {
            "type": "skill_reference",
            "skill_id": self.settings.openai_skill_id,
        }
        if self.settings.openai_skill_version:
            skill_reference["version"] = self.settings.openai_skill_version

        return {
            "agent": {
                "model": self.settings.openai_model,
                "instructions": instructions,
                "reasoning": {"effort": self.settings.openai_reasoning_effort},
                "text": {
                    "format": {"type": "json_schema", "schema": PLAN_RESPONSE_SCHEMA},
                    "verbosity": "low",
                },
            },
            "environment": {
                "type": "openai_hosted",
                "network": {"access": "disabled"},
                "skills": [skill_reference],
            },
            "input": prompt,
            "stream": True,
            "stream_options": {"include_obfuscation": False},
            "metadata": {"application": "tomorrow-desk"},
        }

    async def create_planning_session(
        self,
        completed_tasks: list[str],
        upcoming_tasks: list[str],
    ) -> AgentTurnResult:
        prompt = (
            "다음 업무 목록을 검토해 대화를 시작하세요.\n\n"
            f"오늘 한 업무:\n{self._as_bullets(completed_tasks)}\n\n"
            f"앞으로 할 업무:\n{self._as_bullets(upcoming_tasks)}"
        )
        return await self._create_session(prompt, CHAT_AGENT_INSTRUCTIONS)

    async def continue_planning_session(
        self,
        openai_session_id: str,
        message: str,
        current_plan: list[PlanItem],
    ) -> AgentTurnResult:
        plan_text = self._as_bullets([item.title for item in current_plan])
        prompt = f"사용자 메시지:\n{message}\n\n현재 내일 할 일 초안:\n{plan_text}"
        events = [
            {
                "type": "agent.session.input.message",
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            }
        ]

        client = self._client or self._new_client()
        close_client = self._client is None
        try:
            async with client.stream(
                "GET",
                f"/agents/sessions/{openai_session_id}/events",
                params={"include_obfuscation": "false"},
            ) as stream:
                stream.raise_for_status()
                response = await client.post(
                    f"/agents/sessions/{openai_session_id}/events",
                    json={"events": events},
                    headers={"Idempotency-Key": str(uuid.uuid4())},
                )
                response.raise_for_status()
                output = await self._collect_stream(stream.aiter_lines())
            return self._to_result(openai_session_id, output)
        except (httpx.HTTPError, ValueError) as exc:
            raise AgentServiceError(f"OpenAI Agent 후속 대화에 실패했습니다: {exc}") from exc
        finally:
            if close_client:
                await client.aclose()

    async def finalize_plan(self, plan: list[PlanItem]) -> AgentTurnResult:
        prompt = (
            "사용자가 다음 내일 할 일을 확정했습니다. 항목을 누락하거나 추가하지 말고 "
            "저장용 최종 목록으로 정리하세요.\n\n"
            f"확정할 업무:\n{self._as_bullets([item.title for item in plan])}"
        )
        return await self._create_session(prompt, FINAL_AGENT_INSTRUCTIONS)

    async def _create_session(self, prompt: str, instructions: str) -> AgentTurnResult:
        client = self._client or self._new_client()
        close_client = self._client is None
        try:
            async with client.stream(
                "POST",
                "/agents/sessions",
                json=self._session_payload(prompt, instructions),
            ) as response:
                response.raise_for_status()
                output = await self._collect_stream(response.aiter_lines())
            session_id = output["session_id"]
            if not session_id:
                raise AgentServiceError("OpenAI Agent 세션 ID를 받지 못했습니다.")
            return self._to_result(session_id, output)
        except AgentServiceError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise AgentServiceError(f"OpenAI Agent 세션 생성에 실패했습니다: {exc}") from exc
        finally:
            if close_client:
                await client.aclose()

    async def _collect_stream(self, lines: AsyncIterator[str]) -> dict[str, str]:
        session_id = ""
        output_text = ""
        completed = False
        failed_message = ""

        async for line in lines:
            if not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if not data or data == "[DONE]":
                continue
            event = json.loads(data)
            session_id = event.get("session_id", session_id)
            event_type = event.get("type")
            if event_type == "agent.session.turn.output_text.done":
                output_text = event.get("text", output_text)
            elif event_type == "agent.session.turn.completed":
                completed = True
                break
            elif event_type in {
                "agent.session.turn.failed",
                "agent.session.turn.cancelled",
                "agent.session.failed",
                "error",
            }:
                failed_message = json.dumps(event, ensure_ascii=False)
                break

        if failed_message:
            raise AgentServiceError(f"OpenAI Agent 실행이 완료되지 않았습니다: {failed_message}")
        if not completed:
            raise AgentServiceError("OpenAI Agent 이벤트 스트림이 완료 전에 종료되었습니다.")
        if not output_text:
            raise AgentServiceError("OpenAI Agent가 텍스트 결과를 반환하지 않았습니다.")
        return {"session_id": session_id, "output_text": output_text}

    @staticmethod
    def _to_result(session_id: str, output: dict[str, str]) -> AgentTurnResult:
        try:
            parsed = json.loads(output["output_text"])
            message = str(parsed["assistantMessage"]).strip()
            titles = [
                str(item["title"]).strip() for item in parsed["plan"] if item["title"].strip()
            ]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise AgentServiceError("OpenAI Agent 응답 형식이 올바르지 않습니다.") from exc

        plan = [
            PlanItem(id=f"plan-{uuid.uuid4().hex[:12]}", title=title, completed=False)
            for title in titles
        ]
        return AgentTurnResult(session_id=session_id, assistant_message=message, plan=plan)

    @staticmethod
    def _as_bullets(items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items) if items else "- 없음"
