import asyncio
import json

from app.agent import OpenAIAgentClient
from app.config import Settings


async def line_stream(events):
    for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False)}"


def test_collects_completed_agent_output():
    client = OpenAIAgentClient(Settings(openai_api_key="test-key", storage_backend="memory"))
    output = asyncio.run(
        client._collect_stream(
            line_stream(
                [
                    {"type": "agent.session.created", "session_id": "session-1"},
                    {
                        "type": "agent.session.turn.output_text.done",
                        "session_id": "session-1",
                        "text": '{"assistantMessage":"안녕하세요","plan":[]}',
                    },
                    {"type": "agent.session.turn.completed", "session_id": "session-1"},
                ]
            )
        )
    )
    assert output["session_id"] == "session-1"
    assert "assistantMessage" in output["output_text"]


def test_session_payload_references_configured_skill():
    settings = Settings(
        openai_api_key="test-key",
        storage_backend="memory",
        openai_skill_id="skill_test",
        openai_skill_version="latest",
    )
    client = OpenAIAgentClient(settings)
    payload = client._session_payload("업무", "지침")
    assert payload["agent"]["model"] == "gpt-5.6-sol"
    assert payload["agent"]["reasoning"] == {"effort": "medium"}
    assert payload["environment"]["skills"] == [
        {"type": "skill_reference", "skill_id": "skill_test", "version": "latest"}
    ]
