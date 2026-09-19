"""Resolve and build the LLM client the whole system runs on.

Every model call in this app goes through here: the agent loop and the admin
JSON generator. The connection is a row in `platforms` rather than a value in
`.env`, so changing provider, base URL, key or model is a data change an
administrator can make from the panel instead of a deploy.

Resolution order:

1. the row marked active;
2. otherwise the first row, so a system that has been configured at all always
   has a model;
3. otherwise the DEEPSEEK_* values in `.env`, which is what a brand-new install
   has before anything has been saved.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any, Mapping, NamedTuple, Optional

from langchain_deepseek import ChatDeepSeek
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.platform import Platform

# A client holds an HTTP connection pool, so rebuilding one per call is waste -
# the agent loop used to keep a single client for the whole process for exactly
# that reason. Reuse is keyed on the configuration behind the client, so saving
# an edit in the panel changes the key and the next run picks it up without a
# restart. Small and bounded: only a handful of distinct configurations (the
# agent loop's and the generator's) are ever live at once.
_CACHE_LOCK = threading.Lock()
_CLIENTS: "OrderedDict[tuple, ChatDeepSeek]" = OrderedDict()
_MAX_CACHED_CLIENTS = 8


class LLMConfig(NamedTuple):
    """One resolved connection, detached from the session that loaded it."""

    source: str  # "row" when it came from `platforms`, "env" for the fallback
    platform_id: Optional[int]
    name: str
    base_url: Optional[str]
    api_key: str
    model: str
    temperature: Optional[float]
    max_tokens: Optional[int]
    thinking: bool

    def cache_key(self) -> tuple:
        return (
            self.platform_id,
            self.base_url,
            self.api_key,
            self.model,
            self.temperature,
            self.max_tokens,
            self.thinking,
        )


def config_from_platform(platform: Platform) -> LLMConfig:
    """Snapshot a row. Reading the columns here means the caller can let its
    session go without the config turning into a detached-instance error."""
    return LLMConfig(
        source="row",
        platform_id=platform.id,
        name=platform.name or "LLM",
        base_url=(platform.base_url or "").strip() or None,
        api_key=platform.api_key or "",
        model=(platform.model or "").strip() or "deepseek-chat",
        temperature=platform.temperature,
        max_tokens=platform.max_tokens,
        thinking=bool(platform.thinking),
    )


def active_platform(db: Session) -> Optional[Platform]:
    """The row to run on: the active one, else the first one."""
    platform = (
        db.query(Platform)
        .filter(Platform.is_active.is_(True))
        .order_by(Platform.id.asc())
        .first()
    )
    if platform is not None:
        return platform
    return db.query(Platform).order_by(Platform.id.asc()).first()


def resolve_config(db: Optional[Session] = None) -> LLMConfig:
    """The connection every model call should use right now."""
    owns_session = db is None
    session = db or SessionLocal()
    try:
        platform = active_platform(session)
        if platform is not None:
            return config_from_platform(platform)
        return LLMConfig(
            source="env",
            platform_id=None,
            name="DeepSeek (from .env)",
            base_url=settings.deepseek_base_url or None,
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_model or "deepseek-chat",
            temperature=None,
            max_tokens=None,
            thinking=False,
        )
    finally:
        if owns_session:
            session.close()


def build_chat_model(
    config: LLMConfig,
    *,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float = 180,
    model_kwargs: Optional[Mapping[str, Any]] = None,
) -> ChatDeepSeek:
    """Build, or reuse, a client for `config`.

    `temperature` and `max_tokens` are the caller's defaults; a value set on the
    row wins, because overriding them is the point of configuring the row.
    """
    effective_temperature = config.temperature if config.temperature is not None else temperature
    effective_max_tokens = config.max_tokens if config.max_tokens is not None else max_tokens

    kwargs: dict[str, Any] = {
        "model": config.model,
        # An endpoint that needs no key (a local Ollama or vLLM) still has to be
        # given something: the OpenAI client rejects an empty string.
        "api_key": config.api_key or "not-needed",
        "timeout": timeout,
    }
    if config.base_url:
        kwargs["base_url"] = config.base_url
    if effective_temperature is not None:
        kwargs["temperature"] = effective_temperature
    if effective_max_tokens is not None:
        kwargs["max_tokens"] = effective_max_tokens
    if model_kwargs:
        kwargs["model_kwargs"] = dict(model_kwargs)
    if config.thinking:
        kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

    key = config.cache_key() + (
        timeout,
        effective_temperature,
        effective_max_tokens,
        repr(sorted(model_kwargs.items())) if model_kwargs else "",
    )

    with _CACHE_LOCK:
        cached = _CLIENTS.get(key)
        if cached is not None:
            _CLIENTS.move_to_end(key)
            return cached
        client = ChatDeepSeek(**kwargs)
        _CLIENTS[key] = client
        while len(_CLIENTS) > _MAX_CACHED_CLIENTS:
            _CLIENTS.popitem(last=False)
        return client


def ensure_default_platform(db: Session) -> Optional[Platform]:
    """Move the `.env` DeepSeek values into `platforms` the first time.

    A fresh install is configured through `.env`, which leaves the table empty;
    copying those values in means the panel becomes the one place the connection
    lives from then on. Idempotent - once a row exists nothing is written, so a
    re-run never duplicates or overwrites what an administrator has since set.
    """
    if db.query(Platform).first() is not None:
        return None
    if not settings.deepseek_api_key:
        return None
    platform = Platform(
        name="DeepSeek",
        base_url=settings.deepseek_base_url or None,
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model or "deepseek-chat",
        is_active=True,
    )
    db.add(platform)
    db.commit()
    db.refresh(platform)
    return platform
