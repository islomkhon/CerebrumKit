from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from app.core.database import Base


class Platform(Base):
    """An LLM endpoint the whole system runs on.

    One row is active at a time and both the agent loop and the admin generators
    build their client from it, so moving to another provider, key or model is a
    change an administrator makes in the panel rather than a deploy. When no row
    is marked active the first row is used, so a system that has been configured
    at all always has a model to answer with.

    `base_url` is the OpenAI-compatible root (for example
    https://api.deepseek.com/v1). Keeping it a column is what lets one table hold
    DeepSeek, OpenAI, OpenRouter, Groq or a local vLLM/Ollama server without a
    code change.
    """

    __tablename__ = "platforms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    base_url = Column(String(512), nullable=True)
    api_key = Column(Text, nullable=True)
    model = Column(String(255), nullable=False, default="deepseek-chat")
    # NULL means "keep the caller's default", so a row only has to state what it
    # wants to differ from. The agent loop defaults to 0.7 and no max_tokens;
    # the JSON generator defaults to 0.1 and 4096.
    temperature = Column(Float, nullable=True)
    max_tokens = Column(Integer, nullable=True)
    # Provider-side reasoning switch, sent as
    # extra_body={"thinking": {"type": "enabled"}} when on. Providers that do not
    # know the parameter reject the call, which is what the panel's test button
    # is for.
    thinking = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
