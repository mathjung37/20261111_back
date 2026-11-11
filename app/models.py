from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class PlanItem(ApiModel):
    id: str
    title: str = Field(min_length=1, max_length=500)
    completed: bool = False

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return value.strip()


class CreateWorkSessionRequest(ApiModel):
    completed_tasks: list[str] = Field(default_factory=list, alias="completedTasks")
    upcoming_tasks: list[str] = Field(default_factory=list, alias="upcomingTasks")

    @field_validator("completed_tasks", "upcoming_tasks")
    @classmethod
    def clean_tasks(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]


class WorkSessionResponse(ApiModel):
    session_id: str = Field(alias="sessionId")
    assistant_message: str = Field(alias="assistantMessage")
    plan: list[PlanItem]


class SendMessageRequest(ApiModel):
    message: str = Field(min_length=1, max_length=8000)
    plan: list[PlanItem] = Field(default_factory=list)

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        return value.strip()


class SendMessageResponse(ApiModel):
    assistant_message: str = Field(alias="assistantMessage")
    plan: list[PlanItem]


class FinalizeSessionRequest(ApiModel):
    plan: list[PlanItem] = Field(min_length=1)


class FinalizeSessionResponse(ApiModel):
    saved: bool
    plan_count: int = Field(alias="planCount")


class HealthResponse(ApiModel):
    status: str
    environment: str
    storage: str
    openai_configured: bool = Field(alias="openaiConfigured")
    timestamp: datetime
