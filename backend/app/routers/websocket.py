from datetime import datetime, timezone
import asyncio
import json
import logging
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import base64
import hashlib
import hmac

from app.core.config import settings
from app.core.agent_loop import AgentLoop
from app.core.delegation import set_delegation_sink
from app.core.database import SessionLocal
from app.models.chat import Chat
from app.models.user import User

router = APIRouter(prefix="/ws", tags=["websocket"])
logger = logging.getLogger(__name__)


def decode_jwt(token: str, secret: str) -> dict | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        msg = f"{header_b64}.{payload_b64}".encode()
        expected_sig = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
        rem = len(sig_b64) % 4
        padded = sig_b64 + ("=" * ((4 - rem) % 4))
        actual_sig = base64.urlsafe_b64decode(padded)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        rem2 = len(payload_b64) % 4
        padded2 = payload_b64 + ("=" * ((4 - rem2) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded2))
        exp = payload.get("exp")
        if exp and datetime.now(timezone.utc).timestamp() > exp:
            return None
        return payload
    except Exception:
        return None


def get_user_from_token(token: str) -> dict | None:
    return decode_jwt(token, settings.secret_key)


def authorize_chat_access(user_id: int, chat_id: int) -> bool:
    """Return True when the user is allowed to reach this chat.

    Administrators may reach any chat; everyone else only their own. Without
    this check any authenticated user could subscribe to another user's chat,
    post into it (spending the project's LLM budget) or cancel their run.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None or not user.is_active:
            return False
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if chat is None:
            return False
        if user.role == "admin":
            return True
        return chat.user_id == user.id
    finally:
        db.close()


class ChatConnectionManager:
    def __init__(self):
        self.active: Dict[int, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, chat_id: int):
        await websocket.accept()
        if chat_id not in self.active:
            self.active[chat_id] = set()
        self.active[chat_id].add(websocket)

    def disconnect(self, websocket: WebSocket, chat_id: int):
        self.active.get(chat_id, set()).discard(websocket)
        if not self.active.get(chat_id):
            del self.active[chat_id]

    async def broadcast(self, chat_id: int, message: dict, exclude: WebSocket | None = None):
        for ws in self.active.get(chat_id, set()):
            if ws == exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                pass


manager = ChatConnectionManager()
agent_loop = AgentLoop(broadcast_fn=manager.broadcast)

# A tool body that hands a message to another agent runs on a worker thread and
# has no reference to this object, so it reaches the loop through
# app.core.delegation instead (see app/core/delegation.py).
set_delegation_sink(agent_loop)
active_agent_tasks: Dict[int, asyncio.Task] = {}


async def _broadcast_agent_status(chat_id: int, status: str):
    await manager.broadcast(chat_id, {
        "type": "agent_loop_status",
        "chat_id": chat_id,
        "status": status,
    })


def _agent_loop_running(chat_id: int) -> bool:
    task = active_agent_tasks.get(chat_id)
    return bool(task and not task.done())


def _start_agent_loop(
    chat_id: int,
    content: str,
    sender_id: int | None = None,
    sender_name: str | None = None,
) -> None:
    async def runner():
        await _broadcast_agent_status(chat_id, "running")
        try:
            await agent_loop.execute(
                chat_id=chat_id,
                content=content,
                sender_id=sender_id,
                sender_name=sender_name,
            )
        except asyncio.CancelledError:
            await _broadcast_agent_status(chat_id, "idle")
            raise
        except Exception:
            logger.exception("Agent loop failed for chat %s", chat_id)
            await _broadcast_agent_status(chat_id, "idle")
        else:
            await _broadcast_agent_status(chat_id, "idle")
        finally:
            task = active_agent_tasks.get(chat_id)
            if task is asyncio.current_task():
                active_agent_tasks.pop(chat_id, None)

    active_agent_tasks[chat_id] = asyncio.create_task(runner())


@router.websocket("/chats/{chat_id}")
async def chat_websocket(
    websocket: WebSocket,
    chat_id: int,
    token: str = Query(...),
):
    """WebSocket for real-time chat messaging."""
    # Validate token
    user = get_user_from_token(token)
    if not user:
        await websocket.close(code=4001)
        return

    sender_id = user.get("sub")
    if not sender_id:
        await websocket.close(code=4001)
        return

    # A valid token is not enough: the user must actually be allowed to reach
    # this chat. 4403 = authenticated but forbidden.
    if not authorize_chat_access(int(sender_id), chat_id):
        await websocket.close(code=4403)
        return

    # Get sender info
    sender_name = None
    try:
        db = SessionLocal()
        sender_user = db.query(User).filter(User.id == int(sender_id)).first()
        sender_name = sender_user.name if sender_user else None
    finally:
        db.close()

    await manager.connect(websocket, chat_id)

    try:
        # Inside the try: a client that drops straight after the handshake would
        # otherwise raise WebSocketDisconnect out of the endpoint and log a
        # traceback for every reconnect.
        await websocket.send_json({
            "type": "agent_loop_status",
            "chat_id": chat_id,
            "status": "running" if _agent_loop_running(chat_id) else "idle",
        })

        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type", "message")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if msg_type in {"stop", "stop_agent_loop"}:
                task = active_agent_tasks.get(chat_id)
                if task and not task.done():
                    await _broadcast_agent_status(chat_id, "stopping")
                    task.cancel()
                else:
                    await _broadcast_agent_status(chat_id, "idle")
                continue

            if msg_type == "typing":
                # Forward typing indicator to others in the chat
                await manager.broadcast(chat_id, {
                    "type": "typing",
                    "chat_id": chat_id,
                }, exclude=websocket)
                continue

            if msg_type != "message":
                continue

            content = data.get("content", "").strip()
            if not content:
                continue

            if _agent_loop_running(chat_id):
                await websocket.send_json({
                    "type": "agent_loop_status",
                    "chat_id": chat_id,
                    "status": "busy",
                })
                continue

            # The user message is persisted and broadcast inside the agent loop,
            # which knows the workflow receiver and can set receiver_type/id.
            _start_agent_loop(
                chat_id=chat_id,
                content=content,
                sender_id=int(sender_id) if sender_id else None,
                sender_name=sender_name,
            )

    except WebSocketDisconnect:
        manager.disconnect(websocket, chat_id)
    except Exception:
        manager.disconnect(websocket, chat_id)
