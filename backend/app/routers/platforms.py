"""Admin CRUD for the LLM connections the system runs on.

The active row drives every model call in the app (see app.core.llm), so these
endpoints are admin-only, attached at the router level like the other admin
routers so no individual endpoint can forget the guard.

The API key is returned as stored. It is a working credential for the
configured provider, so this router must stay admin-only: anyone who can read
this list can spend against the account behind it.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.core.llm import active_platform, build_chat_model, config_from_platform
from app.models.platform import Platform

router = APIRouter(
    prefix="/admin/platforms",
    tags=["admin-platforms"],
    dependencies=[Depends(require_admin)],
)


class PlatformIn(BaseModel):
    name: str = Field(..., min_length=1)
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: str = Field(default="deepseek-chat", min_length=1)
    temperature: Optional[float] = Field(default=None, ge=0, le=2)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    thinking: bool = False
    is_active: bool = False


class PlatformOut(BaseModel):
    id: int
    name: str
    base_url: Optional[str]
    api_key: Optional[str]
    model: str
    temperature: Optional[float]
    max_tokens: Optional[int]
    thinking: bool
    is_active: bool
    # True for the row the system would actually run on right now, which is the
    # first row when nothing is flagged active. Purely informational: it lets the
    # panel show the truth instead of making the reader apply the fallback rule.
    effective: bool

    model_config = {"from_attributes": True}


class PlatformTestResult(BaseModel):
    ok: bool
    message: str


def _get_or_404(db: Session, platform_id: int) -> Platform:
    platform = db.query(Platform).filter(Platform.id == platform_id).first()
    if platform is None:
        raise HTTPException(status_code=404, detail="Platform not found")
    return platform


def _effective_id(db: Session) -> Optional[int]:
    platform = active_platform(db)
    return platform.id if platform is not None else None


def _serialize(platform: Platform, effective_id: Optional[int]) -> PlatformOut:
    return PlatformOut(
        id=platform.id,
        name=platform.name,
        base_url=platform.base_url,
        api_key=platform.api_key,
        model=platform.model,
        temperature=platform.temperature,
        max_tokens=platform.max_tokens,
        thinking=bool(platform.thinking),
        is_active=bool(platform.is_active),
        effective=platform.id == effective_id,
    )


def _activate(db: Session, platform: Platform) -> None:
    """Make `platform` the one row that is active.

    Exactly one row is meant to be active, so this is a single transaction that
    clears the others first: two active rows would make which model answers
    depend on row order.
    """
    db.query(Platform).filter(Platform.id != platform.id).update(
        {"is_active": False}, synchronize_session="fetch"
    )
    platform.is_active = True
    db.commit()
    db.refresh(platform)


@router.get("", response_model=List[PlatformOut])
def list_platforms(db: Session = Depends(get_db)):
    effective_id = _effective_id(db)
    rows = db.query(Platform).order_by(Platform.id.asc()).all()
    return [_serialize(row, effective_id) for row in rows]


@router.post("", response_model=PlatformOut, status_code=201)
def create_platform(payload: PlatformIn, db: Session = Depends(get_db)):
    first_row = db.query(Platform).first() is None
    platform = Platform(
        name=payload.name.strip(),
        base_url=(payload.base_url or "").strip() or None,
        api_key=payload.api_key or "",
        model=payload.model.strip(),
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        thinking=payload.thinking,
        # The first connection saved has to be usable immediately, or the panel
        # would create a row that nothing runs on.
        is_active=payload.is_active or first_row,
    )
    db.add(platform)
    db.flush()
    if platform.is_active:
        _activate(db, platform)
    else:
        db.commit()
        db.refresh(platform)
    return _serialize(platform, _effective_id(db))


@router.get("/{platform_id}", response_model=PlatformOut)
def get_platform(platform_id: int, db: Session = Depends(get_db)):
    return _serialize(_get_or_404(db, platform_id), _effective_id(db))


@router.put("/{platform_id}", response_model=PlatformOut)
def update_platform(platform_id: int, payload: PlatformIn, db: Session = Depends(get_db)):
    platform = _get_or_404(db, platform_id)
    platform.name = payload.name.strip()
    platform.base_url = (payload.base_url or "").strip() or None
    platform.api_key = payload.api_key or ""
    platform.model = payload.model.strip()
    platform.temperature = payload.temperature
    platform.max_tokens = payload.max_tokens
    platform.thinking = payload.thinking
    if payload.is_active:
        _activate(db, platform)
    else:
        platform.is_active = False
        db.commit()
        db.refresh(platform)
    return _serialize(platform, _effective_id(db))


@router.post("/{platform_id}/activate", response_model=PlatformOut)
def activate_platform(platform_id: int, db: Session = Depends(get_db)):
    platform = _get_or_404(db, platform_id)
    _activate(db, platform)
    return _serialize(platform, _effective_id(db))


@router.delete("/{platform_id}", status_code=204)
def delete_platform(platform_id: int, db: Session = Depends(get_db)):
    platform = _get_or_404(db, platform_id)
    was_active = bool(platform.is_active)
    db.delete(platform)
    db.flush()
    if was_active:
        # Removing the active connection without promoting another would leave
        # the fallback (the first row) in charge by accident; make it explicit.
        successor = db.query(Platform).order_by(Platform.id.asc()).first()
        if successor is not None:
            successor.is_active = True
    db.commit()


@router.post("/{platform_id}/test", response_model=PlatformTestResult)
def test_platform(platform_id: int, db: Session = Depends(get_db)):
    """Make one small call so a wrong URL, key or model name surfaces here.

    The row is tested as configured, except that temperature and max_tokens are
    pinned low: this is a handshake, not a generation.
    """
    platform = _get_or_404(db, platform_id)
    config = config_from_platform(platform)
    if not config.api_key and not config.base_url:
        return PlatformTestResult(
            ok=False, message="No API key and no base URL: there is nothing to call."
        )
    probe = config._replace(temperature=0.0, max_tokens=64)
    try:
        client = build_chat_model(probe, timeout=30)
        reply = client.invoke([HumanMessage(content="Reply with the single word: ok")])
        text = str(getattr(reply, "content", reply)).strip()
        if text:
            return PlatformTestResult(ok=True, message=f"{config.model} answered: {text[:200]}")
        # A reasoning model can spend the whole budget before it writes any
        # visible text, which still proves the URL, key and model name work.
        return PlatformTestResult(
            ok=True,
            message=f"{config.model} responded with no text content, but the call succeeded.",
        )
    except Exception as exc:  # the provider's own message is the useful part
        return PlatformTestResult(ok=False, message=f"{type(exc).__name__}: {exc}"[:600])
