from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.core.message_page import paginate_messages
from app.models.project import Project
from app.models.user import User
from app.models.agent import Agent
from app.models.chat import Chat
from app.models.message import Message
from app.models.project_table import ProjectTable
from app.routers.storage import _physical_table_names, _reflect_table, _table_info
from app.schemas.auth import UserOut
from app.schemas.schemas import AgentOut, ProjectCreate, ProjectUpdate, ProjectOut, ChatCreate, ChatOut, MessageCreate, MessageOut, MessagePage, StorageTableInfo, AgentPage, UserPage, TablePage

# Client projects router
client_router = APIRouter(prefix="/client/projects", tags=["client-projects"])

# User-facing projects router (used by client dashboard)
router = APIRouter(prefix="/projects", tags=["projects"])

# Admin projects router (used by admin panel).
# The admin guard is attached at the router level so no individual endpoint can
# forget it - this router previously had no role check at all, which let any
# authenticated client manage projects and read other users' chats.
admin_router = APIRouter(
    prefix="/admin/projects",
    tags=["admin-projects"],
    dependencies=[Depends(require_admin)],
)


SYSTEM_PROJECT_LOCKED = (
    "The system project cannot be edited or deleted: the Project Manager agent "
    "lives in it and manages the rest of the system from there."
)


SYSTEM_PROJECT_NO_AGENTS = (
    "The system project must keep at least one agent in a workflow group: that is "
    "what answers in this project. Add an agent before saving."
)


def _refuse_system_project(project: Project) -> None:
    """Stop the system project's own row from being changed or removed."""
    if project.is_system:
        raise HTTPException(status_code=403, detail=SYSTEM_PROJECT_LOCKED)


def _guard_system_workflow(project: Project, workflow: Any) -> None:
    """Let the system project be rewired, but not into a dead end.

    Its name, description and active flag are locked, while the agents in it and
    the workflow that wires them stay editable - that is what lets the Project
    Manager keep managing the system. The one change refused is one that would
    leave every group empty, because then nothing would answer in this project
    and the agent that runs it could no longer be reached.
    """
    if not project.is_system or workflow is None:
        return
    nodes = workflow.get("nodes") if isinstance(workflow, dict) else None
    if not isinstance(nodes, list):
        raise HTTPException(
            status_code=422, detail="workflow must be an object with a nodes list"
        )
    assigned = [
        agent
        for node in nodes
        if isinstance(node, dict) and node.get("type") == "group"
        for agent in (node.get("agents") or [])
    ]
    if not assigned:
        raise HTTPException(status_code=403, detail=SYSTEM_PROJECT_NO_AGENTS)


def _paginate(items: list, page: int, page_size: int) -> tuple[list, int, int, int]:
    """Slice a list into a page. Returns (items, total, page, pages)."""
    page_size = max(1, min(page_size, 100))
    total = len(items)
    pages = max(1, (total + page_size - 1) // page_size) if total else 1
    page = max(1, min(page, pages))
    start = (page - 1) * page_size
    return items[start : start + page_size], total, page, pages


def _resolve_message_names(db: Session, msg_data: dict) -> None:
    """Fill sender_name / receiver_name from users/agents when not provided."""
    if "sender_name" not in msg_data:
        if msg_data.get("sender_type") == "user" and msg_data.get("sender_id"):
            user = db.query(User).filter(User.id == msg_data["sender_id"]).first()
            if user:
                msg_data["sender_name"] = user.name
        elif msg_data.get("sender_id"):
            agent = db.query(Agent).filter(Agent.id == msg_data["sender_id"]).first()
            if agent:
                msg_data["sender_name"] = agent.name
    if "receiver_name" not in msg_data and msg_data.get("receiver_id"):
        if msg_data.get("receiver_type") == "user":
            user = db.query(User).filter(User.id == msg_data["receiver_id"]).first()
            if user:
                msg_data["receiver_name"] = user.name
        elif msg_data.get("receiver_type") == "agent":
            agent = db.query(Agent).filter(Agent.id == msg_data["receiver_id"]).first()
            if agent:
                msg_data["receiver_name"] = agent.name


@admin_router.get("", response_model=List[ProjectOut])
def list_all_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Project).order_by(Project.id.desc()).all()


@admin_router.post("", response_model=ProjectOut)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = Project(
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
        workflow=payload.workflow,
    )
    project.users.append(current_user)
    if payload.user_ids:
        users = db.query(User).filter(User.id.in_(payload.user_ids)).all()
        project.users.extend(users)
    if payload.agent_ids:
        agents = db.query(Agent).filter(Agent.id.in_(payload.agent_ids)).all()
        project.agents.extend(agents)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@admin_router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = (
        db.query(Project)
        .options(
            selectinload(Project.agents).selectinload(Agent.skills),
            selectinload(Project.agents).selectinload(Agent.tools),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@admin_router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = (
        db.query(Project)
        .options(
            selectinload(Project.agents).selectinload(Agent.skills),
            selectinload(Project.agents).selectinload(Agent.tools),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.is_system:
        # The row itself is locked; the workflow that wires its agents is not.
        if any(getattr(payload, key, None) is not None for key in ("name", "description", "is_active")):
            _refuse_system_project(project)
        _guard_system_workflow(project, payload.workflow)
    for key in ("name", "description", "is_active", "workflow"):
        val = getattr(payload, key, None)
        if val is not None:
            setattr(project, key, val)
    db.commit()
    db.refresh(project)
    return project


@admin_router.delete("/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _refuse_system_project(project)
    db.delete(project)
    db.commit()
    return {"ok": True}


@admin_router.get("/{project_id}/workflow")
def get_project_workflow(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    wf = project.workflow
    if isinstance(wf, str):
        import json
        try:
            wf = json.loads(wf)
        except json.JSONDecodeError:
            pass
    return wf or {"nodes": [], "wires": []}


@admin_router.get("/{project_id}/agents", response_model=AgentPage)
def list_project_agents(
    project_id: int,
    search: str = "",
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    agents = sorted(project.agents, key=lambda a: a.name.lower())
    if search.strip():
        s = search.strip().lower()
        agents = [a for a in agents if s in a.name.lower()]
    items, total, page, pages = _paginate(agents, page, page_size)
    return AgentPage(items=items, total=total, page=page, page_size=page_size, pages=pages)


@admin_router.post("/{project_id}/agents/{agent_id}", response_model=AgentOut)
def assign_agent_to_project(
    project_id: int,
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    agent = (
        db.query(Agent)
        .options(selectinload(Agent.skills), selectinload(Agent.tools))
        .filter(Agent.id == agent_id)
        .first()
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent not in project.agents:
        project.agents.append(agent)
        db.commit()
        db.refresh(project)
    return agent


@admin_router.delete("/{project_id}/agents/{agent_id}")
def remove_agent_from_project(
    project_id: int,
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if agent in project.agents:
        project.agents.remove(agent)
        db.commit()
    return {"ok": True}


@admin_router.get("/{project_id}/available-agents", response_model=AgentPage)
def list_available_agents(
    project_id: int,
    search: str = "",
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    assigned_ids = [a.id for a in project.agents]
    q = db.query(Agent).filter(~Agent.id.in_(assigned_ids))
    if search.strip():
        s = f"%{search.strip()}%"
        q = q.filter(Agent.name.ilike(s))
    total = q.count()
    page_size = max(1, min(page_size, 100))
    pages = max(1, (total + page_size - 1) // page_size) if total else 1
    page = max(1, min(page, pages))
    items = q.order_by(Agent.name).offset((page - 1) * page_size).limit(page_size).all()
    return AgentPage(items=items, total=total, page=page, page_size=page_size, pages=pages)


@admin_router.get("/{project_id}/users/{user_id}/chats", response_model=List[ChatOut])
def list_user_chats(
    project_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return (
        db.query(Chat)
        .filter(Chat.project_id == project_id, Chat.user_id == user_id)
        .order_by(Chat.created_at.desc())
        .all()
    )


@admin_router.post("/{project_id}/users/{user_id}/chats", response_model=ChatOut)
def create_user_chat(
    project_id: int,
    user_id: int,
    payload: ChatCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    chat = Chat(
        project_id=project_id,
        user_id=user_id,
        description=(payload.description or ""),
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


@admin_router.get("/{project_id}/users/{user_id}/chats/{chat_id}", response_model=ChatOut)
def get_user_chat(
    project_id: int,
    user_id: int,
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = (
        db.query(Chat)
        .filter(Chat.id == chat_id, Chat.project_id == project_id, Chat.user_id == user_id)
        .first()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@admin_router.put("/{project_id}/users/{user_id}/chats/{chat_id}", response_model=ChatOut)
def update_user_chat(
    project_id: int,
    user_id: int,
    chat_id: int,
    payload: ChatCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = (
        db.query(Chat)
        .filter(Chat.id == chat_id, Chat.project_id == project_id, Chat.user_id == user_id)
        .first()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    d = payload.model_dump(exclude={'user_id', 'project_id'})
    for key, val in d.items():
        if val is not None:
            setattr(chat, key, val)
    db.commit()
    db.refresh(chat)
    return chat


@admin_router.delete("/{project_id}/users/{user_id}/chats/{chat_id}")
def delete_user_chat(
    project_id: int,
    user_id: int,
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = (
        db.query(Chat)
        .filter(Chat.id == chat_id, Chat.project_id == project_id, Chat.user_id == user_id)
        .first()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    db.delete(chat)
    db.commit()
    return {"ok": True}


@admin_router.get("/{project_id}/users/{user_id}/chats/{chat_id}/messages", response_model=MessagePage)
def list_chat_messages(
    project_id: int,
    user_id: int,
    chat_id: int,
    limit: Optional[int] = Query(default=None, ge=1, le=200),
    before_id: Optional[int] = Query(default=None),
    include_debug: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Newest page of the chat, or the page just before `before_id`.

    Debug rows are only sent when they are asked for: they are most of the
    bytes in a long conversation and the normal view filters them out anyway.
    """
    chat = (
        db.query(Chat)
        .filter(Chat.id == chat_id, Chat.project_id == project_id, Chat.user_id == user_id)
        .first()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return paginate_messages(db, chat_id, limit=limit, before_id=before_id, include_debug=include_debug)


@admin_router.post("/{project_id}/users/{user_id}/chats/{chat_id}/messages", response_model=MessageOut)
def send_chat_message(
    project_id: int,
    user_id: int,
    chat_id: int,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = (
        db.query(Chat)
        .filter(Chat.id == chat_id, Chat.project_id == project_id, Chat.user_id == user_id)
        .first()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    msg_data = payload.model_dump(exclude_unset=True)
    msg_data["chat_id"] = chat_id
    if current_user.role == "admin":
        msg_data.setdefault("sender_type", "user")
        if msg_data.get("sender_type") == "user":
            msg_data.setdefault("sender_id", current_user.id)
    else:
        # Non-admins cannot forge the sender: attribute the message to the
        # authenticated user rather than trusting the request body.
        msg_data["sender_type"] = "user"
        msg_data["sender_id"] = current_user.id
        msg_data["sender_name"] = current_user.name
    _resolve_message_names(db, msg_data)
    msg = Message(**msg_data)
    db.add(msg)
    db.flush()
    chat.last_message_id = msg.id
    chat.new_messages_count = db.query(Message).filter(Message.chat_id == chat_id).count()
    db.commit()
    db.refresh(msg)
    return msg


@admin_router.get("/{project_id}/users", response_model=UserPage)
def list_project_users(
    project_id: int,
    search: str = "",
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    users = sorted(project.users, key=lambda u: (u.name or "").lower())
    if search.strip():
        s = search.strip().lower()
        users = [u for u in users if s in ((u.name or "") + " " + (u.email or "")).lower()]
    items, total, page, pages = _paginate(users, page, page_size)
    return UserPage(items=items, total=total, page=page, page_size=page_size, pages=pages)


@admin_router.post("/{project_id}/users/{user_id}", response_model=UserOut)
def assign_user_to_project(
    project_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user not in project.users:
        project.users.append(user)
        db.commit()
        db.refresh(project)
    return user


@admin_router.delete("/{project_id}/users/{user_id}")
def remove_user_from_project(
    project_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    user = db.query(User).filter(User.id == user_id).first()
    if user in project.users:
        project.users.remove(user)
        db.commit()
    return {"ok": True}


# ── Client routes ─────────────────────────────────────────────


@client_router.get("", response_model=List[ProjectOut])
def list_client_projects(
    search: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return only projects that the current user belongs to."""
    q = (
        db.query(Project)
        .join(Project.users)
        .filter(User.id == current_user.id)
        .order_by(Project.id.desc())
    )
    if search.strip():
        s = f"%{search.strip()}%"
        q = q.filter(Project.name.ilike(s))
    return q.all()


@client_router.get("/{project_id}/chats", response_model=List[ChatOut])
def list_client_chats(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return chats for the current user in this project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return (
        db.query(Chat)
        .filter(Chat.project_id == project_id, Chat.user_id == current_user.id)
        .order_by(Chat.created_at.desc())
        .all()
    )


@client_router.post("/{project_id}/chats", response_model=ChatOut)
def create_client_chat(
    project_id: int,
    payload: ChatCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new chat. project_id and user_id are set automatically."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # Without this, a client could open a chat inside a project they are not
    # assigned to, and the project's agent workflow would answer them.
    if current_user.role != "admin" and not any(
        member.id == current_user.id for member in project.users
    ):
        raise HTTPException(
            status_code=403, detail="You do not have access to this project"
        )
    chat = Chat(
        project_id=project_id,
        user_id=current_user.id,
        description=(payload.description or ""),
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


@client_router.get("/{project_id}/chats/{chat_id}", response_model=ChatOut)
def get_client_chat(
    project_id: int,
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = (
        db.query(Chat)
        .filter(Chat.id == chat_id, Chat.project_id == project_id, Chat.user_id == current_user.id)
        .first()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@client_router.put("/{project_id}/chats/{chat_id}", response_model=ChatOut)
def update_client_chat(
    project_id: int,
    chat_id: int,
    payload: ChatCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = (
        db.query(Chat)
        .filter(Chat.id == chat_id, Chat.project_id == project_id, Chat.user_id == current_user.id)
        .first()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    d = payload.model_dump(exclude={"user_id", "project_id"})
    for key, val in d.items():
        if val is not None:
            setattr(chat, key, val)
    db.commit()
    db.refresh(chat)
    return chat


@client_router.delete("/{project_id}/chats/{chat_id}")
def delete_client_chat(
    project_id: int,
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = (
        db.query(Chat)
        .filter(Chat.id == chat_id, Chat.project_id == project_id, Chat.user_id == current_user.id)
        .first()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    db.delete(chat)
    db.commit()
    return {"ok": True}


@client_router.get("/{project_id}/chats/{chat_id}/messages", response_model=MessagePage)
def list_client_chat_messages(
    project_id: int,
    chat_id: int,
    limit: Optional[int] = Query(default=None, ge=1, le=200),
    before_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Newest page of the chat, or the page just before `before_id`."""
    chat = (
        db.query(Chat)
        .filter(Chat.id == chat_id, Chat.project_id == project_id, Chat.user_id == current_user.id)
        .first()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    # A client never sees tool or flow rows, so they are not sent at all.
    return paginate_messages(db, chat_id, limit=limit, before_id=before_id, include_debug=False)


@client_router.post("/{project_id}/chats/{chat_id}/messages", response_model=MessageOut)
def send_client_chat_message(
    project_id: int,
    chat_id: int,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = (
        db.query(Chat)
        .filter(Chat.id == chat_id, Chat.project_id == project_id, Chat.user_id == current_user.id)
        .first()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    msg_data = payload.model_dump(exclude_unset=True)
    msg_data["chat_id"] = chat_id
    msg_data.setdefault("sender_type", "user")
    if msg_data.get("sender_type") == "user":
        msg_data.setdefault("sender_id", current_user.id)
    _resolve_message_names(db, msg_data)
    msg = Message(**msg_data)
    db.add(msg)
    db.flush()
    chat.last_message_id = msg.id
    chat.new_messages_count = db.query(Message).filter(Message.chat_id == chat_id).count()
    db.commit()
    db.refresh(msg)
    return msg


@admin_router.get("/{project_id}/available-users", response_model=UserPage)
def list_available_users(
    project_id: int,
    search: str = "",
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    assigned_ids = [u.id for u in project.users]
    q = db.query(User).filter(~User.id.in_(assigned_ids))
    if search.strip():
        s = f"%{search.strip()}%"
        q = q.filter((User.name.ilike(s)) | (User.email.ilike(s)))
    total = q.count()
    page_size = max(1, min(page_size, 100))
    pages = max(1, (total + page_size - 1) // page_size) if total else 1
    page = max(1, min(page, pages))
    items = q.order_by(User.name).offset((page - 1) * page_size).limit(page_size).all()
    return UserPage(items=items, total=total, page=page, page_size=page_size, pages=pages)

@admin_router.get("/{project_id}/tables", response_model=TablePage)
def list_project_tables(
    project_id: int,
    search: str = "",
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    assigned = [
        row[0]
        for row in db.query(ProjectTable.table_name)
        .filter(ProjectTable.project_id == project_id)
        .order_by(ProjectTable.table_name)
        .all()
    ]
    if search.strip():
        s = search.strip().lower()
        assigned = [name for name in assigned if s in name.lower()]
    result = []
    for name in assigned:
        try:
            result.append(_table_info(db, name))
        except HTTPException:
            continue
    items, total, page, pages = _paginate(result, page, page_size)
    return TablePage(items=items, total=total, page=page, page_size=page_size, pages=pages)


@admin_router.post("/{project_id}/tables/{table_name}", response_model=StorageTableInfo)
def assign_table_to_project(
    project_id: int,
    table_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _reflect_table(table_name, db.connection())  # 404 if the table does not exist in the database
    existing = (
        db.query(ProjectTable)
        .filter(
            ProjectTable.project_id == project_id,
            ProjectTable.table_name == table_name,
        )
        .first()
    )
    if not existing:
        db.add(ProjectTable(project_id=project_id, table_name=table_name))
        db.commit()
    return _table_info(db, table_name)


@admin_router.delete("/{project_id}/tables/{table_name}")
def remove_table_from_project(
    project_id: int,
    table_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.query(ProjectTable).filter(
        ProjectTable.project_id == project_id,
        ProjectTable.table_name == table_name,
    ).delete()
    db.commit()
    return {"ok": True}


@admin_router.get("/{project_id}/available-tables", response_model=TablePage)
def list_available_tables(
    project_id: int,
    search: str = "",
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    assigned = {
        row[0]
        for row in db.query(ProjectTable.table_name).filter(ProjectTable.project_id == project_id).all()
    }
    query = search.strip().lower()
    result = []
    for name in _physical_table_names():
        if name in assigned:
            continue
        if query and query not in name.lower():
            continue
        try:
            result.append(_table_info(db, name))
        except HTTPException:
            continue
    items, total, page, pages = _paginate(result, page, page_size)
    return TablePage(items=items, total=total, page=page, page_size=page_size, pages=pages)
