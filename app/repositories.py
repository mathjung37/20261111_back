from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Protocol

from app.errors import SessionNotFoundError


class WorkSessionRepository(Protocol):
    async def create(self, session_id: str, data: dict[str, Any]) -> None: ...

    async def get(self, session_id: str) -> dict[str, Any]: ...

    async def add_message(self, session_id: str, role: str, content: str) -> None: ...

    async def update_plan(self, session_id: str, plan: list[dict[str, Any]]) -> None: ...

    async def finalize(
        self,
        session_id: str,
        submitted_plan: list[dict[str, Any]],
        final_plan: list[dict[str, Any]],
        final_agent_session_id: str,
    ) -> None: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


class InMemoryWorkSessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[str, dict[str, Any]] = {}

    async def create(self, session_id: str, data: dict[str, Any]) -> None:
        now = utc_now()
        self.sessions[session_id] = {
            **deepcopy(data),
            "messages": [],
            "status": "planning",
            "created_at": now,
            "updated_at": now,
        }

    async def get(self, session_id: str) -> dict[str, Any]:
        if session_id not in self.sessions:
            raise SessionNotFoundError(session_id)
        return deepcopy(self.sessions[session_id])

    async def add_message(self, session_id: str, role: str, content: str) -> None:
        session = await self.get(session_id)
        session["messages"].append({"role": role, "content": content, "created_at": utc_now()})
        session["updated_at"] = utc_now()
        self.sessions[session_id] = session

    async def update_plan(self, session_id: str, plan: list[dict[str, Any]]) -> None:
        session = await self.get(session_id)
        session["plan"] = deepcopy(plan)
        session["updated_at"] = utc_now()
        self.sessions[session_id] = session

    async def finalize(
        self,
        session_id: str,
        submitted_plan: list[dict[str, Any]],
        final_plan: list[dict[str, Any]],
        final_agent_session_id: str,
    ) -> None:
        session = await self.get(session_id)
        session.update(
            {
                "submitted_plan": deepcopy(submitted_plan),
                "final_plan": deepcopy(final_plan),
                "final_agent_session_id": final_agent_session_id,
                "status": "finalized",
                "finalized_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        self.sessions[session_id] = session


class FirestoreWorkSessionRepository:
    def __init__(self, project_id: str | None, collection: str) -> None:
        import firebase_admin
        from firebase_admin import firestore

        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app(options={"projectId": project_id} if project_id else None)

        self._firestore = firestore
        self._client = firestore.client()
        self._collection = self._client.collection(collection)

    async def create(self, session_id: str, data: dict[str, Any]) -> None:
        payload = {
            **data,
            "status": "planning",
            "created_at": self._firestore.SERVER_TIMESTAMP,
            "updated_at": self._firestore.SERVER_TIMESTAMP,
        }
        await asyncio.to_thread(self._collection.document(session_id).set, payload)

    async def get(self, session_id: str) -> dict[str, Any]:
        snapshot = await asyncio.to_thread(self._collection.document(session_id).get)
        if not snapshot.exists:
            raise SessionNotFoundError(session_id)
        return snapshot.to_dict()

    async def add_message(self, session_id: str, role: str, content: str) -> None:
        await self.get(session_id)
        reference = self._collection.document(session_id)
        message = {
            "role": role,
            "content": content,
            "created_at": self._firestore.SERVER_TIMESTAMP,
        }
        await asyncio.to_thread(reference.collection("messages").document().set, message)
        await asyncio.to_thread(
            reference.update,
            {"updated_at": self._firestore.SERVER_TIMESTAMP},
        )

    async def update_plan(self, session_id: str, plan: list[dict[str, Any]]) -> None:
        await self.get(session_id)
        await asyncio.to_thread(
            self._collection.document(session_id).update,
            {"plan": plan, "updated_at": self._firestore.SERVER_TIMESTAMP},
        )

    async def finalize(
        self,
        session_id: str,
        submitted_plan: list[dict[str, Any]],
        final_plan: list[dict[str, Any]],
        final_agent_session_id: str,
    ) -> None:
        await self.get(session_id)
        await asyncio.to_thread(
            self._collection.document(session_id).update,
            {
                "submitted_plan": submitted_plan,
                "final_plan": final_plan,
                "final_agent_session_id": final_agent_session_id,
                "status": "finalized",
                "finalized_at": self._firestore.SERVER_TIMESTAMP,
                "updated_at": self._firestore.SERVER_TIMESTAMP,
            },
        )
