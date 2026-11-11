class AgentServiceError(RuntimeError):
    """OpenAI Agents API request failed or returned unusable output."""


class SessionNotFoundError(LookupError):
    """Requested application session does not exist."""
