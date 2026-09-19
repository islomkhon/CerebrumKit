"""The bridge a tool body uses to run another agent.

A tool body executes on a worker thread: `AgentLoop._call_tool` hands it to
`loop.run_in_executor`, precisely so a slow tool cannot block the event loop.
An agent run, though, is a coroutine - it calls the LLM, writes messages and
broadcasts to the chat. So a tool that wants to delegate cannot simply `await`;
it has to hand the coroutine back to the loop the chat runs on and block until
it finishes, which is what `call_agent` below does.

`routers.websocket` registers the one AgentLoop it serves chats with, and
`AgentLoop.execute` records the loop a run is on, so the two halves are wired
without a tool body ever seeing either object.

Like `project_id` and `chat_id` (see `tool_exec.SYSTEM_VARIABLES`), nothing here
is a model-supplied argument: the tool body passes what the run gave it.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, Optional

logger = logging.getLogger(__name__)

# How long a tool body waits for the nested run. Deliberately below
# `agent_loop.DELEGATION_CALL_TIMEOUT_SECONDS`: a nested run that runs long is
# then reported by this module, with a reason, instead of being cut off by the
# caller's own tool timeout with a generic "did not finish" message.
CALL_TIMEOUT_SECONDS = 270

# The AgentLoop instance the websocket router serves chats with. A tool body has
# no route to the caller's object, so the router leaves it here.
_sink: Any = None

# The event loop that instance runs on. A nested run may only be scheduled on
# the loop the chat is already running on, and a worker thread cannot discover
# it, so `AgentLoop.execute` records it here.
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_delegation_sink(sink: Any) -> None:
    """Register the AgentLoop that delegated runs execute on."""
    global _sink
    _sink = sink


def bind_event_loop(loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    """Remember the loop the agent loop runs on (defaults to the current one)."""
    global _main_loop
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
    _main_loop = loop


def unavailable_reason() -> Optional[str]:
    """Why delegation cannot run right now, or None when it can."""
    if _sink is None:
        return "no agent loop is registered"
    if _main_loop is None or _main_loop.is_closed():
        return "no chat run has started on this process yet"
    return None


def call_agent(
    *,
    target_agent_id: int,
    message: str,
    chat_id: int,
    project_id: int,
    caller_agent_id: Optional[int] = None,
    caller_name: Optional[str] = None,
    call_depth: int = 0,
    timeout: int = CALL_TIMEOUT_SECONDS,
) -> str:
    """Run another agent with `message` and return what it answered.

    Called by a tool body, on a worker thread, and therefore blocking. The
    return value is written to be handed straight back to the model, so every
    failure is a sentence rather than an exception.
    """
    # Imported here because app.core.agent_loop imports this module.
    from app.core.agent_loop import MAX_DELEGATION_DEPTH

    if call_depth >= MAX_DELEGATION_DEPTH:
        return (
            f"Cannot delegate because agents are already {call_depth} levels deep "
            f"and the limit is {MAX_DELEGATION_DEPTH}. Answer from what you already "
            "have instead of calling another agent."
        )
    if not isinstance(target_agent_id, int) or isinstance(target_agent_id, bool):
        return "Cannot delegate because agent_id must be an integer"
    if not isinstance(message, str) or not message.strip():
        return "Cannot delegate because message is empty"

    reason = unavailable_reason()
    if reason:
        return f"Cannot delegate because {reason}"

    # A tool body runs on a worker thread, which is what makes blocking here
    # safe. Calling from the event loop itself would instead wait for a
    # coroutine that the loop cannot start until this call returns, so the whole
    # server would stall until the timeout. Refuse instead of hanging.
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    if current_loop is _main_loop:
        return (
            "Cannot delegate because this call is running on the event loop thread; "
            "waiting here would block the server. Tools call this from a worker thread"
        )

    try:
        future = asyncio.run_coroutine_threadsafe(
            _sink.run_delegated(
                target_agent_id=target_agent_id,
                message=message,
                chat_id=chat_id,
                project_id=project_id,
                caller_agent_id=caller_agent_id,
                caller_name=caller_name,
                # The depth travels with the run that is calling, not with the
                # registered sink: a chain A -> B -> C must reach depth 2, and C
                # calls through this same sink.
                call_depth=call_depth,
            ),
            _main_loop,
        )
    except Exception as exc:
        logger.exception("Could not schedule a delegated run of agent %s", target_agent_id)
        return f"Cannot delegate because the run could not be scheduled: {exc}"

    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError:
        future.cancel()
        logger.warning(
            "Delegated run of agent %s did not finish within %ss", target_agent_id, timeout
        )
        return (
            f"Cannot delegate because agent {target_agent_id} did not answer within "
            f"{timeout} seconds"
        )
    except Exception as exc:
        logger.exception("Delegated run of agent %s failed", target_agent_id)
        return f"Cannot delegate because the agent run failed: {exc}"
