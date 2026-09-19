"""Legacy chat endpoints.

These routes are authenticated and ownership-scoped: administrators can reach
any chat, everyone else only their own. The role-scoped /admin/projects and
/client/projects routers are the primary API used by the frontend.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.message_page import paginate_messages
from app.models.chat import Chat
from app.models.message import Message
from app.models.project import Project
from app.models.user import User
from app.models.agent import Agent
from app.schemas.schemas import ChatCreate, ChatOut, MessageCreate, MessageOut, MessagePage

router = APIRouter(prefix="/chats", tags=["chats"])


def _is_admin(user: User) -> bool:
    return user.role == "admin"


def _may_use_project(db: Session, project_id: int | None, user: User) -> bool:
    """Whether a caller may hold a chat inside this project.

    A chat's project decides which workflow answers in it, so a chat inside a
    project the caller cannot otherwise reach is an escalation path rather than
    a data problem: the System project's Project Manager agent creates users,
    projects, agents, skills, tools and tables, and a tool body is arbitrary
    Python. This is the same rule the /client/projects chat routes apply.
    """
    if project_id is None:
        return False
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        return False
    return any(member.id == user.id for member in project.users)


def _get_chat_or_404(db: Session, chat_id: int, current_user: User) -> Chat:
    """Fetch a chat, enforcing ownership for non-admin callers.

    Missing and not-yours both return 404 so chat ids stay unenumerable.
    """
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if chat is None or (not _is_admin(current_user) and chat.user_id != current_user.id):
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@router.get("", response_model=List[ChatOut])
def list_chats(
    project_id: int | None = None,
    user_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Chat)
    if project_id is not None:
        q = q.filter(Chat.project_id == project_id)
    if _is_admin(current_user):
        # Administrators may look at any user's chats.
        if user_id is not None:
            q = q.filter(Chat.user_id == user_id)
    else:
        # Non-admins are always restricted to their own chats.
        q = q.filter(Chat.user_id == current_user.id)
    return q.all()


@router.post("", response_model=ChatOut)
def create_chat(
    payload: ChatCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = payload.model_dump()
    if not _is_admin(current_user):
        # A caller cannot create chats on behalf of somebody else, nor inside a
        # project they are not a member of.
        data["user_id"] = current_user.id
        if not _may_use_project(db, data.get("project_id"), current_user):
            raise HTTPException(
                status_code=403, detail="You do not have access to this project"
            )
    chat = Chat(**data)
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


@router.get("/{chat_id}", response_model=ChatOut)
def get_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_chat_or_404(db, chat_id, current_user)


@router.put("/{chat_id}", response_model=ChatOut)
def update_chat(
    chat_id: int,
    payload: ChatCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = _get_chat_or_404(db, chat_id, current_user)
    for key, val in payload.model_dump().items():
        if key == "user_id" and not _is_admin(current_user):
            # Ownership cannot be reassigned by a non-admin.
            continue
        if key == "project_id" and val != chat.project_id:
            # Moving a chat moves which project's workflow answers in it, so the
            # destination is checked the same way creation is. A None or
            # unchanged value is left alone rather than re-evaluated: the
            # payload always carries every key, and clearing the project would
            # otherwise follow from a request that only meant to edit the
            # description.
            if not _is_admin(current_user) and not _may_use_project(db, val, current_user):
                raise HTTPException(
                    status_code=403, detail="You do not have access to this project"
                )
            if val is None:
                continue
        setattr(chat, key, val)
    db.commit()
    db.refresh(chat)
    return chat


@router.delete("/{chat_id}")
def delete_chat(
    chat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = _get_chat_or_404(db, chat_id, current_user)
    db.delete(chat)
    db.commit()
    return {"ok": True}


@router.get("/{chat_id}/messages", response_model=MessagePage)
def list_messages(
    chat_id: int,
    limit: Optional[int] = Query(default=None, ge=1, le=200),
    before_id: Optional[int] = Query(default=None),
    include_debug: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_chat_or_404(db, chat_id, current_user)
    return paginate_messages(db, chat_id, limit=limit, before_id=before_id, include_debug=include_debug)


@router.post("/{chat_id}/messages", response_model=MessageOut)
def create_message(
    chat_id: int,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat = _get_chat_or_404(db, chat_id, current_user)
    msg_data = payload.model_dump(exclude_unset=True)
    msg_data["chat_id"] = chat_id
    if not _is_admin(current_user):
        # Non-admins cannot forge the sender: the message is always attributed
        # to the authenticated user, never to an agent or another person.
        msg_data["sender_type"] = "user"
        msg_data["sender_id"] = current_user.id
        msg_data["sender_name"] = current_user.name
    if "sender_name" not in msg_data and msg_data.get("sender_id"):
        if msg_data.get("sender_type") == "user":
            sender = db.query(User).filter(User.id == msg_data["sender_id"]).first()
            if sender:
                msg_data["sender_name"] = sender.name
        else:
            sender = db.query(Agent).filter(Agent.id == msg_data["sender_id"]).first()
            if sender:
                msg_data["sender_name"] = sender.name
    if "receiver_name" not in msg_data and msg_data.get("receiver_id"):
        if msg_data.get("receiver_type") == "user":
            receiver = db.query(User).filter(User.id == msg_data["receiver_id"]).first()
            if receiver:
                msg_data["receiver_name"] = receiver.name
        elif msg_data.get("receiver_type") == "agent":
            receiver = db.query(Agent).filter(Agent.id == msg_data["receiver_id"]).first()
            if receiver:
                msg_data["receiver_name"] = receiver.name
    msg = Message(**msg_data)
    db.add(msg)
    db.flush()
    chat.last_message_id = msg.id
    chat.new_messages_count = (
        db.query(Message).filter(Message.chat_id == chat_id).count()
    )
    db.commit()
    db.refresh(msg)
    return msg
