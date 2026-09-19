from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field
from app.schemas.auth import UserOut


# ── Agent ──
class AgentContextToolIn(BaseModel):
    """One pre-run tool on an agent create/edit payload.

    `position` is not accepted from the client: the order of the list is the
    order the block is injected in, so there is nothing extra to keep in sync.
    """

    tool_id: int
    comment: Optional[str] = None
    arguments: Optional[str] = None


class AgentContextToolOut(BaseModel):
    tool_id: int
    name: str = ""
    comment: Optional[str] = None
    arguments: Optional[str] = None
    position: int = 0
    is_active: bool = True


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    skill_ids: list[int] = Field(default_factory=list)
    is_active: bool = True
    # None means "not part of this payload": a PUT that omits the field leaves
    # the agent's existing context tools alone, while an explicit [] clears
    # them. Without that distinction any older client would silently wipe them.
    context_tools: Optional[list[AgentContextToolIn]] = None


class AgentOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    skill_ids: list[int] = Field(default_factory=list)
    tool_ids: list[int] = Field(default_factory=list)
    context_tools: list[AgentContextToolOut] = Field(default_factory=list)
    is_active: bool

    model_config = {"from_attributes": True}


# ── Skill ──
class SkillCreate(BaseModel):
    name: str
    description: Optional[str] = None
    tool_ids: list[int] = Field(default_factory=list)
    is_active: bool = True


class SkillOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    tool_ids: list[int] = Field(default_factory=list)
    is_active: bool

    model_config = {"from_attributes": True}


# ── Tool ──
class ToolCreate(BaseModel):
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    body: Optional[str] = None
    is_active: bool = True


class ToolOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    body: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}


# ── Project ──
class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True
    workflow: Optional[list] = None
    user_ids: Optional[list[int]] = None
    agent_ids: Optional[list[int]] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    workflow: Optional[Any] = None


class ProjectOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_active: bool
    is_system: bool = False
    workflow: Optional[Any] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Chat ──
class ChatCreate(BaseModel):
    user_id: Optional[int] = None
    project_id: Optional[int] = None
    description: Optional[str] = None


class ChatOut(BaseModel):
    id: int
    user_id: int
    project_id: int
    new_messages_count: int
    last_message_id: Optional[int] = None
    description: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Message ──
class MessageCreate(BaseModel):
    chat_id: Optional[int] = None
    sender_type: str  # "user" or "agent"
    sender_id: Optional[int] = None
    sender_name: Optional[str] = None
    receiver_type: Optional[str] = None  # "user" or "agent"
    receiver_id: Optional[int] = None
    receiver_name: Optional[str] = None
    message_type: str = "text"
    content: Optional[str] = None


class MessageOut(BaseModel):
    id: int
    chat_id: int
    sender_type: str
    sender_id: Optional[int] = None
    sender_name: Optional[str] = None
    receiver_type: Optional[str] = None
    receiver_id: Optional[int] = None
    receiver_name: Optional[str] = None
    message_type: str
    content: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MessagePage(BaseModel):
    """One page of a chat history, oldest row first."""

    messages: List[MessageOut]
    has_more: bool

    model_config = {"from_attributes": True}


# ── ProjectTable ──
class ProjectSummaryOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class StorageColumnInfo(BaseModel):
    name: str
    data_type: str
    description: str | None = None
    editor_type: str | None = None
    length: int | None = None
    nullable: bool = True
    default_value: Any = None


class StorageTableInfo(BaseModel):
    """A physical table read directly from the database."""

    name: str
    description: str | None = None
    columns: list[StorageColumnInfo] = Field(default_factory=list)
    row_count: int = 0
    projects: list[ProjectSummaryOut] = Field(default_factory=list)
    is_system: bool = False


class StorageColumnInput(BaseModel):
    name: str
    data_type: str = "string"
    description: str | None = None
    length: int | None = None
    nullable: bool = True
    default_value: Any = None


class StorageTableCreate(BaseModel):
    name: str
    description: str | None = None
    columns: list[StorageColumnInput] = Field(default_factory=list)


class StorageTableUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    columns: list[StorageColumnInput] | None = None

class StorageRowOut(BaseModel):
    id: int
    data: dict[str, Any]
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None


class StorageRowPage(BaseModel):
    items: list[StorageRowOut]
    total: int
    page: int
    per_page: int
    pages: int


class StorageRowPayload(BaseModel):
    data: dict[str, Any]


# --- Paginated list responses (admin projects members) ---
class AgentPage(BaseModel):
    items: list[AgentOut]
    total: int
    page: int
    page_size: int
    pages: int


class UserPage(BaseModel):
    items: list[UserOut]
    total: int
    page: int
    page_size: int
    pages: int


class TablePage(BaseModel):
    items: list[StorageTableInfo]
    total: int
    page: int
    page_size: int
    pages: int
