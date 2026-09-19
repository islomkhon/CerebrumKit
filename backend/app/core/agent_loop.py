"""
Agent workflow executor — ported from Laravel AgentLoop job.

Walks a project's workflow DAG (start → group → stop), calls DeepSeek
via langchain-deepseek (ChatDeepSeek) for each assigned agent, saves messages
to DB, and broadcasts them live through the WebSocket connection manager.

A group's agents run one after another, in the order they were assigned. How
much chat history an agent sees and what it shows in the chat are fixed in the
constants below instead of being stored in the workflow: the workflow only
wires agents together.

A tool body can also hand a whole message to another agent - see
`app.core.delegation`. That runs as a nested agent instance: its own tool rounds
are capped by DELEGATED_TOOL_ROUNDS, and how deep such a chain may go is capped
by MAX_DELEGATION_DEPTH, so two agents that ask each other cannot loop forever.
"""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Awaitable, Optional, Any

from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from app.core import delegation
from app.core.database import SessionLocal
from app.core.llm import build_chat_model, resolve_config
from app.core.tool_exec import tool_exec
from app.models import Agent, AgentContextTool, Project, Chat, Message, Tool, User
from app.schemas.schemas import MessageOut

logger = logging.getLogger(__name__)

# Async function type: (chat_id: int, payload: dict) -> None
BroadcastFn = Callable[[int, dict], Awaitable[None]]

# Reusable thread pool for running synchronous LLM calls
_llm_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="llm")

# Tool bodies are arbitrary blocking Python (an HTTP request can take seconds),
# so they get their own pool. Sharing one pool with the LLM calls meant a single
# slow tool could starve every other chat's model request.
_tool_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="tool")

# Guard against infinite tool-call loops from the model
MAX_TOOL_CALL_ROUNDS = 100

# A tool that never returns must not hang the run forever. The worker thread
# itself cannot be killed, so this only frees the run: the call still finishes,
# and can still commit its own writes, in the background.
TOOL_CALL_TIMEOUT_SECONDS = 60

# Tool output is fed straight back to the model, so one large API response must
# not be allowed to consume the context window.
MAX_TOOL_RESULT_CHARS = 8000

# A body over the cap is trimmed *inside* its JSON rather than cut off: a model
# holding half a JSON object cannot tell what it is missing, so it re-issues the
# same call and burns its tool budget instead of answering. One round drops
# items from the largest list, so this only needs a handful of passes.
MAX_TOOL_TRIM_ROUNDS = 6
TOOL_TRIM_MARKER = "_omitted"
_MAX_TOOL_TRIM_DEPTH = 3

# The audit card stored under a tool call is read by a person, so it keeps far
# more of the result than the model is handed. It is still bounded: the card is
# a chat message, and an unbounded body would sit in every later fetch of the
# chat, so a result past this is cut with the same marker as the model's copy.
MAX_TOOL_AUDIT_CHARS = 100000

# Safety net for a malformed or cyclic workflow.
MAX_WORKFLOW_STEPS = 200

# How many agents deep a run may delegate. A tool that calls another agent hands
# the callee `call_depth + 1` (see tool_exec.SYSTEM_VARIABLES); at this depth the
# call is refused, so two agents that call each other cannot loop forever.
MAX_DELEGATION_DEPTH = 3

# A delegated run has to answer inside the caller's turn, which is itself capped
# by a tool timeout, so it gets a much smaller tool budget than a run a person
# started.
DELEGATED_TOOL_ROUNDS = 8

# A tool that runs another agent blocks its worker thread until that whole
# nested run has finished, which does not fit the budget of an ordinary tool.
# The name in the tool's JSON spec is what identifies one; the system seeder
# takes the name from here, so the two cannot drift apart.
DELEGATION_TOOL_NAMES = frozenset({"call_agent"})
DELEGATION_CALL_TIMEOUT_SECONDS = 300

# Per-run behaviour for every agent. These used to be stored per agent inside
# the workflow JSON (showOutput / showToolOutput / historyWindow / qty); the
# workflow now only wires agents together, so they live here.
SHOW_AGENT_OUTPUT = True   # persist and broadcast each agent's reply
SHOW_TOOL_OUTPUT = True    # record every tool call as its own input/output message
HISTORY_WINDOW = 0         # earlier chat messages handed to the agent

# The agent's own last reply in this chat is handed back to it, so a follow-up
# ("and for X?", "now do the same for Y") lands on an agent that already has its
# own earlier findings and framing in view, instead of one that starts from
# nothing on every message. Where it goes is a choice:
#
# "history" - the reply enters the message list as the agent's own previous
#   turn, immediately before the user message the model is answering, so the
#   model reads a conversation that already happened rather than a briefing
#   about one.
# "system" - the reply is appended to the system prompt instead.
# "off" - nothing is injected.
#
# Either way it is re-sent on every tool round of the run, and with a history
# window above 0 the same reply can also appear among the windowed messages.
INJECT_LAST_AGENT_MESSAGE_MODE = "history"
# A stored reply can be a whole table - the weather runs are pages of JSON - so
# only the tail is injected. The tail is kept because that is where an answer
# states its conclusion.
MAX_LAST_AGENT_MESSAGE_CHARS = 2000

# How much pre-fetched context the agent's own pre-run tools may add to one
# system prompt. Each tool's output is already cut to MAX_TOOL_RESULT_CHARS;
# this is the ceiling for all of them together, so an agent configured with a
# long list cannot push the conversation out of the model's window. An entry
# that no longer fits is dropped and counted rather than cut, because half a
# JSON object invites the model to call the tool again to fill the gap.
MAX_CONTEXT_TOOL_TOTAL_CHARS = 24000


def _get_llm() -> ChatDeepSeek:
    """Return the client agent instances run on.

    Built from the row `platforms` marks active (see app.core.llm), so changing
    provider, key or model from the panel takes effect on the next run instead of
    the next restart. The client is still reused while the configuration behind
    it is unchanged, because rebuilding one discards its HTTP connection pool.
    """
    return build_chat_model(resolve_config(), temperature=0.7, timeout=180)


class AgentLoop:
    """
    Executes a project workflow for a given user message.

    Parameters
    ----------
    broadcast_fn : async callable
        An async function that accepts (chat_id: int, payload: dict)
        and broadcasts to all WebSocket clients in that chat room.
    """

    def __init__(self, broadcast_fn: BroadcastFn, call_depth: int = 0):
        self.broadcast = broadcast_fn
        # How deep this run is in a chain of agents calling agents. A run a
        # person started is 0; see MAX_DELEGATION_DEPTH.
        self.call_depth = call_depth

    # ── Public entry point ──────────────────────────────────────────────

    async def execute(
        self,
        chat_id: int,
        content: str,
        sender_id: Optional[int] = None,
        sender_name: Optional[str] = None,
    ) -> None:
        # A delegated run has to be scheduled on the loop this run is on, and a
        # worker thread cannot discover it, so record it here (see delegation).
        delegation.bind_event_loop()
        db: Session = SessionLocal()
        try:
            chat = db.query(Chat).filter(Chat.id == chat_id).first()
            if not chat or not chat.project_id:
                return

            project = db.query(Project).filter(Project.id == chat.project_id).first()
            workflow = project.workflow if project else None
            if isinstance(workflow, str):
                try:
                    workflow = json.loads(workflow)
                except (json.JSONDecodeError, TypeError):
                    workflow = None

            nodes = workflow.get("nodes", []) if workflow else []
            wires = workflow.get("wires", []) if workflow else []
            nodes_by_id = {node.get("id"): node for node in nodes}
            start_node = next((n for n in nodes if n.get("type") == "start"), None)

            if not project or not workflow or not nodes or not start_node:
                # No workflow can receive this message - persist and broadcast it
                # here so the chat still records it.
                user_msg = self._save_message(
                    chat_id=chat_id,
                    sender_type="user",
                    content=content,
                    db=db,
                    sender_id=sender_id,
                    sender_name=sender_name,
                )
                await self._broadcast_message(user_msg)
                return

            # The workflow knows where this message is directed: the first agent
            # it reaches. That instance saves the visible user message; every
            # other agent instance logs the input as a flow message.
            receiver_agent = self._first_target_agent(workflow, db)

            # Use iterative stack instead of recursion to avoid deep recursion limits.
            # Each entry carries the input text plus the entity (user or agent) that
            # produced it, so message passing can be logged as it flows through agents.
            user_source = {
                "sender_type": "user",
                "sender_id": sender_id,
                "sender_name": sender_name,
            }
            stack = [(start_node["id"], content, user_source)]
            visited = set()
            steps = 0

            while stack:
                steps += 1
                if steps > MAX_WORKFLOW_STEPS:
                    logger.warning(
                        "Workflow for chat %s exceeded %s steps; aborting run",
                        chat_id,
                        MAX_WORKFLOW_STEPS,
                    )
                    break

                node_id, input_text, source = stack.pop()
                if (node_id, input_text) in visited:
                    continue
                visited.add((node_id, input_text))

                node = nodes_by_id.get(node_id)
                if not node:
                    continue

                node_type = node.get("type", "")

                if node_type == "stop":
                    continue

                if node_type == "start":
                    for next_id in self._next_ids(node_id, wires):
                        stack.append((next_id, input_text, source))
                    continue

                if node_type == "group":
                    agents_data = node.get("agents", [])
                    if not agents_data:
                        for next_id in self._next_ids(node_id, wires):
                            stack.append((next_id, input_text, source))
                        continue

                    # Where this input came from (user or previous agent(s)).
                    flow_sender_type = source.get("sender_type", "user")
                    flow_sender_id = source.get("sender_id")
                    flow_sender_name = source.get("sender_name")

                    # Where this group's output goes next: the first agent of the
                    # next group node, or back to the user for the final group.
                    next_agent = self._next_target_agent(workflow, node_id, db)
                    output_receiver_type = "agent" if next_agent else "user"
                    output_receiver_id = next_agent.id if next_agent else None

                    # Agents run one at a time, in the order they were assigned.
                    # A group can still point at an agent that was deleted after
                    # it was assigned. Those are resolved out first, so the run
                    # neither spends an LLM call on an agent that has no row nor
                    # numbers the agents that do run with a gap.
                    runnable = []
                    for agent_data in agents_data:
                        agent_id = agent_data.get("id", 0)
                        agent = (
                            db.query(Agent)
                            .options(selectinload(Agent.tools))
                            .filter(Agent.id == agent_id)
                            .first()
                        )
                        if agent is None:
                            logger.warning(
                                "Group %s in project %s points at missing agent %s; skipping it",
                                node_id,
                                project.id,
                                agent_id,
                            )
                            continue
                        runnable.append((agent_id, agent))

                    outputs = []
                    for position, (agent_id, agent) in enumerate(runnable, start=1):
                        # The workflow keeps a copy of the name the agent had
                        # when it was assigned, which goes stale on a rename.
                        # Run and log under the live name instead.
                        agent_name = agent.name
                        description = (agent.description + " ") if agent.description else ""
                        tools, tool_id_by_name = self._agent_tool_specs(agent)
                        system_prompt = f"You are {agent_name}. {description} . You must provide a helpful and concise response. Use tools efficiently — narrow lookups, small limits, targeted gets, short outputs, less data in/out."
                        # Hand the agent its own last answer in this chat, so a
                        # follow-up continues the earlier work instead of
                        # restarting cold. Read once here rather than inside
                        # _run_agent_instance, so a delegated run - which is not
                        # answering after that reply but on someone else's
                        # request - still starts clean.
                        prior_reply = None
                        if INJECT_LAST_AGENT_MESSAGE_MODE != "off":
                            previous = self._last_agent_message(db, chat_id, agent_id)
                            if previous:
                                tail = self._tail(previous, MAX_LAST_AGENT_MESSAGE_CHARS)
                                if INJECT_LAST_AGENT_MESSAGE_MODE == "system":
                                    system_prompt += (
                                        "\n\nYour own last reply in this conversation "
                                        "was:\n" + tail
                                    )
                                else:
                                    prior_reply = tail
                        result = await self._run_agent_instance(
                            chat_id=chat_id,
                            project_id=project.id,
                            agent_id=agent_id,
                            name=agent_name,
                            index=position,
                            system_prompt=system_prompt,
                            input_text=input_text,
                            prior_reply=prior_reply,
                            save_flow=not (
                                flow_sender_type == "user"
                                and receiver_agent is not None
                                and agent_id == receiver_agent.id
                            ),
                            flow_sender_type=flow_sender_type,
                            flow_sender_id=flow_sender_id,
                            flow_sender_name=flow_sender_name,
                            receiver_type=output_receiver_type,
                            receiver_id=output_receiver_id,
                            tools=tools,
                            tool_id_by_name=tool_id_by_name,
                        )
                        if result is None:  # stop sentinel
                            return
                        outputs.append(result)

                    combined = self._combine_outputs(outputs, input_text)
                    output_source = self._output_source(outputs)

                    for next_id in self._next_ids(node_id, wires):
                        stack.append((next_id, combined, output_source))

        finally:
            db.close()

    async def run_delegated(
        self,
        *,
        target_agent_id: int,
        message: str,
        chat_id: int,
        project_id: int,
        caller_agent_id: Optional[int] = None,
        caller_name: Optional[str] = None,
        call_depth: int = 0,
    ) -> str:
        """Run another agent inside the caller's chat and return its reply.

        Called by a tool body through `app.core.delegation`, so this runs on the
        chat's event loop while the tool's worker thread waits for the string it
        returns. Every failure is a sentence, because the caller is a model.

        `call_depth` is the depth of the run that is delegating (a tool sees it
        as a system variable), and this run is one deeper. The callee must be a
        member of the same project, so a nested run can never widen what the
        calling agent can already reach.
        """
        depth = call_depth + 1
        if depth > MAX_DELEGATION_DEPTH:
            return self._delegation_refusal(target_agent_id, call_depth)

        db: Session = SessionLocal()
        try:
            chat = db.query(Chat).filter(Chat.id == chat_id).first()
            if chat is None or chat.project_id != project_id:
                return (
                    "Cannot delegate because this chat does not belong to the "
                    "project the run is in"
                )

            agent = (
                db.query(Agent)
                .options(selectinload(Agent.tools))
                .filter(Agent.id == target_agent_id)
                .first()
            )
            if agent is None:
                return f"Cannot delegate because there is no agent with id {target_agent_id}"
            if not agent.is_active:
                return f"Cannot delegate because agent '{agent.name}' is not active"

            project = db.query(Project).filter(Project.id == project_id).first()
            if project is None:
                return f"Cannot delegate because there is no project with id {project_id}"
            if not any(member.id == agent.id for member in project.agents):
                return (
                    f"Cannot delegate to '{agent.name}' (agent {agent.id}) because it is "
                    f"not a member of project {project.id}; assign it to the project first"
                )

            description = (agent.description + " ") if agent.description else ""
            system_prompt = (
                f"You are {agent.name}. {description} . You must provide a helpful "
                "and concise response. "
                f"The agent {caller_name or caller_agent_id} delegated this request "
                "to you. Answer the request itself and hand a result back to that "
                "agent; it is the one answering the user."
            )
            tools, tool_id_by_name = self._agent_tool_specs(agent)

            # A fresh loop instance, one level deeper, so the tools *this* run
            # calls see the right depth. The same broadcast function is kept, so
            # the nested run's messages land in the same chat.
            nested = AgentLoop(broadcast_fn=self.broadcast, call_depth=depth)
            result = await nested._run_agent_instance(
                chat_id=chat_id,
                project_id=project_id,
                agent_id=agent.id,
                name=agent.name,
                index=1,
                system_prompt=system_prompt,
                input_text=message,
                # The request is logged in the flow, not as a user bubble: the
                # user did not write it, the delegated agent's caller did.
                save_flow=True,
                flow_sender_type="agent" if caller_agent_id else "user",
                flow_sender_id=caller_agent_id,
                flow_sender_name=caller_name,
                receiver_type="agent" if caller_agent_id else "user",
                receiver_id=caller_agent_id,
                tools=tools,
                tool_id_by_name=tool_id_by_name,
                max_rounds=DELEGATED_TOOL_ROUNDS,
            )

            if not result:
                return f"Cannot delegate because agent '{agent.name}' did not answer"
            if result.get("failed"):
                return (
                    f"Cannot delegate because agent '{agent.name}' failed: "
                    f"{result.get('content') or 'no detail'}"
                )
            content = result.get("content") or ""
            return f"{agent.name} answered:\n{content}"
        finally:
            db.close()

    @staticmethod
    def _delegation_refusal(target_agent_id: int, call_depth: int) -> str:
        return (
            f"Cannot delegate to agent {target_agent_id} because agents are already "
            f"{call_depth} levels deep and the limit is {MAX_DELEGATION_DEPTH}. "
            "Answer from what you already have."
        )

    async def _run_agent_instance(
        self,
        chat_id: int,
        project_id: int,
        agent_id: int,
        name: str,
        index: int,
        system_prompt: str,
        input_text: str,
        prior_reply: Optional[str] = None,
        save_flow: bool = False,
        flow_sender_type: str = "user",
        flow_sender_id: Optional[int] = None,
        flow_sender_name: Optional[str] = None,
        receiver_type: str = "user",
        receiver_id: Optional[int] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        tool_id_by_name: Optional[dict[str, int]] = None,
        max_rounds: Optional[int] = None,
    ) -> Optional[dict]:
        """
        Execute a single agent instance: call LLM, save message, broadcast.
        Returns the output dict, or None if the stop sentinel was triggered.

        `prior_reply` is this agent's own last answer in the chat (already
        trimmed by the caller). It is placed in the message list as the turn
        before the one being answered; see INJECT_LAST_AGENT_MESSAGE_MODE.
        """
        # Each agent run gets its own DB session
        db = SessionLocal()
        agent_label = name
        typing_started = False
        try:
            # Who the run answers. The chat's owner rather than whoever typed:
            # an administrator can post into another user's chat, and a tool
            # acting "for the current user" should act for the one whose chat
            # this is. Resolved here, not passed in, so every caller of this
            # method - including a delegated run - gets it.
            chat_row = db.query(Chat).filter(Chat.id == chat_id).first()
            user_id = chat_row.user_id if chat_row else None
            # Broadcast typing indicator
            await self.broadcast(chat_id, {
                "type": "typing",
                "user_name": agent_label,
            })
            typing_started = True

            # Save the message as it arrives at this agent. The first agent that
            # receives the original user message persists it as the visible text
            # message; every other incoming input is logged as a flow message.
            input_msg = self._save_message(
                chat_id=chat_id,
                sender_type=flow_sender_type,
                content=input_text,
                db=db,
                sender_id=flow_sender_id,
                sender_name=flow_sender_name,
                receiver_type="agent",
                receiver_id=agent_id,
                message_type="text" if not save_flow else "flow",
            )
            await self._broadcast_message(input_msg)

            # The tools the admin marked as "always needed" run here, and
            # their output joins the system prompt. Done after the message is
            # saved and the typing indicator is up, so a slow lookup reads as
            # the agent working instead of as a dead chat.
            system_prompt = await self._with_context_tools(
                system_prompt=system_prompt,
                agent_id=agent_id,
                project_id=project_id,
                chat_id=chat_id,
                user_id=user_id,
                db=db,
            )

            # Build message list with optional chat history
            msgs = [SystemMessage(content=system_prompt)]

            if HISTORY_WINDOW > 0:
                recent = db.query(Message).filter(
                    Message.chat_id == chat_id,
                ).order_by(Message.id.desc()).limit(HISTORY_WINDOW).all()
                for m in reversed(recent):
                    if m.sender_type == "user":
                        msgs.append(HumanMessage(content=m.content))
                    else:
                        # Assistant / agent messages become AIMessage. The
                        # speaker's name is what identifies the agent here,
                        # because sender_type only holds the kind of sender.
                        speaker = m.sender_name or m.sender_type
                        msgs.append(AIMessage(content=f"{speaker}: {m.content}"))

            if prior_reply:
                # The agent's own previous turn, put back in front of the new
                # message so the model answers a follow-up to it rather than
                # cold-starting. It is marked as a quotation of itself so the
                # model reads it as something it already said, not as an
                # instruction or as text it is still in the middle of writing.
                msgs.append(
                    AIMessage(
                        content=(
                            "[Your own last reply in this conversation]\n"
                            + prior_reply
                        )
                    )
                )

            msgs.append(HumanMessage(content=input_text))

            response = await self._invoke_llm_with_tools(
                messages=msgs,
                tools=tools or [],
                tool_id_by_name=tool_id_by_name or {},
                project_id=project_id,
                chat_id=chat_id,
                agent_id=agent_id,
                agent_name=agent_label,
                receiver_type=receiver_type,
                receiver_id=receiver_id,
                show_tool_output=SHOW_TOOL_OUTPUT,
                show_agent_output=SHOW_AGENT_OUTPUT,
                db=db,
                user_id=user_id,
                max_rounds=max_rounds,
            )

            content = self._message_text(response)
            if not content:
                # Every tool round was spent without the model returning an
                # answer, so record that instead of saving an empty bubble.
                content = (
                    f"[{agent_label} returned no answer after "
                    f"{max_rounds or MAX_TOOL_CALL_ROUNDS} tool rounds]"
                )

            await self._stop_typing(chat_id, agent_label, typing_started)
            typing_started = False

            if SHOW_AGENT_OUTPUT:
                # sender_type records the kind of sender, so the agent's
                # own label belongs in sender_name, which is what the chat
                # renders next to the bubble.
                msg = self._save_message(
                    chat_id=chat_id,
                    sender_type="agent",
                    content=content,
                    db=db,
                    sender_id=agent_id,
                    sender_name=agent_label,
                    receiver_type=receiver_type,
                    receiver_id=receiver_id,
                )
                await self._broadcast_message(msg)

            return {"agent_name": name, "index": index, "agent_id": agent_id, "content": content}

        except Exception as e:
            logger.exception("Agent %s #%s failed", name, index)
            await self._stop_typing(chat_id, agent_label, typing_started)
            typing_started = False
            return {
                "agent_name": name,
                "index": index,
                "agent_id": agent_id,
                "content": f"Error: {e}",
                "failed": True,
            }
        finally:
            await self._stop_typing(chat_id, agent_label, typing_started)
            db.close()

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _next_ids(node_id: int, wires: list[dict]) -> list[int]:
        return [w["toNode"] for w in wires if w.get("fromNode") == node_id]

    @staticmethod
    def _first_target_agent(workflow: dict, db: Session) -> Optional[Agent]:
        """Return the first agent the workflow directs messages to, or None."""
        if not isinstance(workflow, dict):
            return None
        nodes = workflow.get("nodes", [])
        wires = workflow.get("wires", [])
        nodes_by_id = {node.get("id"): node for node in nodes}
        start_node = next((n for n in nodes if n.get("type") == "start"), None)
        if not start_node:
            return None
        stack = [start_node["id"]]
        visited = set()
        while stack:
            node_id = stack.pop()
            if node_id in visited:
                continue
            visited.add(node_id)
            node = nodes_by_id.get(node_id)
            if not node:
                continue
            if node.get("type") == "group":
                agents_data = node.get("agents", [])
                if agents_data:
                    agent_id = agents_data[0].get("id")
                    if agent_id:
                        return db.query(Agent).filter(Agent.id == agent_id).first()
            stack.extend(AgentLoop._next_ids(node_id, wires))
        return None

    @staticmethod
    def _next_target_agent(workflow: dict, node_id: int, db: Session) -> Optional[Agent]:
        """Return the first agent of the next group node after `node_id`, or None."""
        if not isinstance(workflow, dict):
            return None
        nodes_by_id = {n.get("id"): n for n in workflow.get("nodes", [])}
        for next_id in AgentLoop._next_ids(node_id, workflow.get("wires", [])):
            node = nodes_by_id.get(next_id)
            if node and node.get("type") == "group":
                agents_data = node.get("agents", [])
                if agents_data:
                    agent_id = agents_data[0].get("id")
                    if agent_id:
                        return db.query(Agent).filter(Agent.id == agent_id).first()
        return None

    @staticmethod
    def _output_source(outputs: list[dict]) -> dict:
        """Describe who produced a group's combined output (for flow logging)."""
        if not outputs:
            return {"sender_type": "user", "sender_id": None}
        if len(outputs) == 1:
            return {"sender_type": "agent", "sender_id": outputs[0].get("agent_id")}
        return {"sender_type": "agents", "sender_id": None}

    @staticmethod
    def _agent_tool_specs(agent: Optional[Agent]) -> tuple[list[dict[str, Any]], dict[str, int]]:
        if not agent:
            return [], {}

        tools = []
        tool_id_by_name = {}
        for tool in agent.tools:
            if not tool.is_active or not tool.description:
                continue
            try:
                spec = json.loads(tool.description)
            except json.JSONDecodeError:
                logger.warning("Skipping tool %s: description is not valid JSON", tool.id)
                continue
            if not isinstance(spec, dict):
                logger.warning("Skipping tool %s: description JSON is not an object", tool.id)
                continue

            function_def = spec.get("function")
            if isinstance(function_def, dict) and function_def.get("name"):
                tool_name = str(function_def["name"])
            elif spec.get("name"):
                tool_name = str(spec["name"])
            else:
                tool_name = tool.name

            tools.append(spec)
            tool_id_by_name[tool_name] = tool.id
        return tools, tool_id_by_name

    @staticmethod
    def _context_tool_arguments(raw: Optional[str]) -> dict[str, Any]:
        """The stored JSON object for a pre-run tool, or {} for none.

        Arguments are normalised on save, so anything unreadable here is a row
        written outside the admin API. Treated as "no arguments" rather than
        raising, so one bad config row cannot take the agent down.
        """
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Ignoring unreadable context tool arguments: %r", raw)
            return {}
        return parsed if isinstance(parsed, dict) else {}

    async def _with_context_tools(
        self,
        *,
        system_prompt: str,
        agent_id: int,
        project_id: int,
        chat_id: int,
        user_id: Optional[int],
        db: Session,
    ) -> str:
        """The system prompt with the agent's pre-run tool output appended.

        These are the lookups an admin configured as always needed (see
        models.AgentContextTool). They run before the model is called at all,
        so the agent opens on the data rather than spending a tool round
        asking for it - and cannot skip it by deciding it knows enough.

        A tool that fails contributes its short error line instead of aborting
        the run: one misconfigured entry must not take the agent down, and a
        visible failure is how the admin finds out.
        """
        agent = (
            db.query(Agent)
            .options(
                selectinload(Agent.context_tool_links).selectinload(
                    AgentContextTool.tool
                )
            )
            .filter(Agent.id == agent_id)
            .first()
        )
        links = list(agent.context_tool_links) if agent else []
        if not links:
            return system_prompt

        sections: list[str] = []
        used = 0
        omitted = 0
        for link in links:
            tool = link.tool
            if tool is None or not tool.is_active:
                continue
            result = await self._execute_tool_call(
                project_id=project_id,
                chat_id=chat_id,
                agent_id=agent_id,
                tool_name=tool.name,
                tool_args=self._context_tool_arguments(link.arguments),
                tool_id_by_name={tool.name: tool.id},
                user_id=user_id,
            )
            text = self._fit_model_text(result)
            if used + len(text) > MAX_CONTEXT_TOOL_TOTAL_CHARS:
                omitted += 1
                continue
            used += len(text)
            heading = link.comment or f"{tool.name} output"
            sections.append(f"### {heading}\n{text}")

        if not sections and not omitted:
            return system_prompt

        block = [
            "Pre-fetched context for this message. It was retrieved with your "
            "own tools before you were called, so use it directly and do not "
            "call a tool again just to obtain the same data:"
        ]
        block.extend(sections)
        if omitted:
            block.append(
                f"({omitted} further pre-fetched result(s) were left out to "
                "keep this prompt within its size budget.)"
            )
        return system_prompt + "\n\n" + "\n\n".join(block)

    async def _invoke_llm_with_tools(
        self,
        messages: list,
        tools: list[dict[str, Any]],
        tool_id_by_name: dict[str, int],
        project_id: int,
        chat_id: int,
        agent_id: int,
        agent_name: str,
        receiver_type: str = "user",
        receiver_id: Optional[int] = None,
        show_tool_output: bool = False,
        show_agent_output: bool = False,
        db: Optional[Session] = None,
        user_id: Optional[int] = None,
        max_rounds: Optional[int] = None,
    ) -> AIMessage:
        loop = asyncio.get_running_loop()
        llm = _get_llm()
        runnable = llm.bind_tools(tools) if tools else llm

        response = await loop.run_in_executor(
            _llm_executor,
            lambda: runnable.invoke(messages),
        )

        for _ in range(max_rounds or MAX_TOOL_CALL_ROUNDS):
            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                return response

            messages.append(response)
            # [dropped-message-fix]
            # The model normally narrates before it calls a tool ("I'll fetch the
            # weather for every city first"). That text belongs to the turn just
            # as much as the answer does, so it is persisted and broadcast like
            # any other agent message. Dropping it made the chat jump straight
            # from the question to the tool cards.
            # if show_agent_output and db is not None:
                # await self._save_interim_text(
                    # content=self._message_text(response),
                    # chat_id=chat_id,
                    # agent_id=agent_id,
                    # agent_name=agent_name,
                    # receiver_type=receiver_type,
                    # receiver_id=receiver_id,
                    # db=db,
                # )
            # Every call in the batch starts at once, so announce them all up
            # front instead of emitting one "typing" per call as each came up.
            for tool_call in tool_calls:
                await self.broadcast(chat_id, {
                    "type": "typing",
                    "user_name": self._tool_label(tool_call.get("name")),
                })

            # The model is only shown these results once the whole batch has
            # been folded back into `messages` below, so as far as the
            # transcript is concerned the calls are independent and there is
            # nothing to serialise: they run concurrently, and a batch of N
            # costs the slowest call rather than the sum of all of them.
            # Concurrency is bounded by _tool_executor; calls past that queue.
            #
            # Gather first, write to the chat second. The debug cards and the
            # ToolMessages then follow the order the model asked for, not the
            # order the calls happened to finish in.
            results = await asyncio.gather(*[
                self._execute_tool_call(
                    project_id=project_id,
                    chat_id=chat_id,
                    agent_id=agent_id,
                    user_id=user_id,
                    tool_name=tool_call.get("name"),
                    tool_args=tool_call.get("args") or {},
                    tool_id_by_name=tool_id_by_name,
                )
                for tool_call in tool_calls
            ])

            for tool_call, result in zip(tool_calls, results):
                tool_name = tool_call.get("name")
                tool_call_id = tool_call.get("id") or tool_name or "tool_call"
                tool_args = tool_call.get("args") or {}
                tool_label = self._tool_label(tool_name)
                # [dropped-message-fix]
                # Pair the typing indicator above, so the chat does not keep
                # showing "Tool: ... is typing" after the call is done.
                # await self._stop_typing(chat_id, tool_label, True)
                # What the model is handed and what the audit card shows, both
                # produced by one serialisation of the result. Dumping it twice
                # costs tens of milliseconds of blocked event loop per call on a
                # multi-megabyte response, for every call in the batch.
                tool_text, audit_text = self._tool_texts(result)
                if show_tool_output and db is not None:
                    # Each tool call is recorded as its own message holding the
                    # input and the output, so a run can be audited afterwards.
                    # It is addressed back to the calling agent, which keeps it
                    # out of the normal chat view: it is meant for debug mode.
                    msg = self._save_message(
                        chat_id=chat_id,
                        sender_type="tool",
                        sender_name=tool_label,
                        content=self._format_tool_output(
                            tool_name, tool_args, result, output=audit_text
                        ),
                        db=db,
                        # The sender is the tool that ran, not the agent that
                        # called it; the agent is already the receiver here.
                        sender_id=tool_id_by_name.get(tool_name or ""),
                        receiver_type="agent",
                        receiver_id=agent_id,
                        message_type="tool",
                    )
                    await self._broadcast_message(msg)
                messages.append(ToolMessage(
                    content=tool_text,
                    tool_call_id=tool_call_id,
                    name=tool_name,
                ))

            response = await loop.run_in_executor(
                _llm_executor,
                lambda: runnable.invoke(messages),
            )

        # [dropped-message-fix]
        # The budget ran out while the model was still asking for tools. Those
        # calls are not executed — one message must not drive unlimited tool
        # calls — but what it said on the way is still worth keeping. Returning
        # an empty reply makes the caller report the run as cut short instead of
        # presenting that narration as if it were a finished answer.
        if getattr(response, "tool_calls", None):
            # if show_agent_output and db is not None:
                # await self._save_interim_text(
                    # content=self._message_text(response),
                    # chat_id=chat_id,
                    # agent_id=agent_id,
                    # agent_name=agent_name,
                    # receiver_type=receiver_type,
                    # receiver_id=receiver_id,
                    # db=db,
                # )
            return AIMessage(content="")
        return response

    # [dropped-message-fix] Persists text the model emitted alongside tool calls.
    async def _save_interim_text(
        self,
        *,
        content: str,
        chat_id: int,
        agent_id: int,
        agent_name: str,
        receiver_type: str,
        receiver_id: Optional[int],
        db: Session,
    ) -> None:
        """Persist text an agent produced while it was still calling tools.

        It is addressed to the same receiver as the agent's final answer, so a
        reader of the chat sees the sentence where it belongs instead of the
        conversation jumping straight from the question to the tool cards.
        """
        if not content:
            return
        msg = self._save_message(
            chat_id=chat_id,
            sender_type="agent",
            content=content,
            db=db,
            sender_id=agent_id,
            sender_name=agent_name,
            receiver_type=receiver_type,
            receiver_id=receiver_id,
        )
        await self._broadcast_message(msg)

    @staticmethod
    def _tool_label(tool_name: Optional[str]) -> str:
        """The name a tool shows in the chat, used for its typing indicator."""
        return f"Tool: {tool_name or 'Unknown'}"

    async def _execute_tool_call(
        self,
        *,
        project_id: int,
        chat_id: int,
        agent_id: int,
        tool_name: Optional[str],
        tool_args: dict[str, Any],
        tool_id_by_name: dict[str, int],
        user_id: Optional[int] = None,
    ) -> Any:
        """Resolve one call to a tool and run it.

        Kept free of DB writes and broadcasts on purpose: a whole batch of these
        is gathered concurrently, and everything that touches the transcript is
        done afterwards, in the order the model asked for the calls.
        """
        tool_id = tool_id_by_name.get(tool_name or "")
        if tool_id is None:
            return f'Cannot execute tool because "{tool_name}" does not belong to this agent'
        # A tool that runs another agent waits on that whole nested run, so it
        # gets the longer budget; everything else keeps the ordinary one.
        timeout = (
            DELEGATION_CALL_TIMEOUT_SECONDS
            if tool_name in DELEGATION_TOOL_NAMES
            else TOOL_CALL_TIMEOUT_SECONDS
        )
        return await self._call_tool(
            project_id=project_id,
            chat_id=chat_id,
            agent_id=agent_id,
            tool_id=tool_id,
            tool_args=tool_args,
            timeout=timeout,
            user_id=user_id,
        )

    async def _call_tool(
        self,
        project_id: int,
        chat_id: int,
        agent_id: int,
        tool_id: int,
        tool_args: dict[str, Any],
        timeout: int = TOOL_CALL_TIMEOUT_SECONDS,
        user_id: Optional[int] = None,
    ) -> Any:
        """Run one tool on the tool pool, bounded by `timeout` seconds.

        A tool body is blocking Python, so it is kept off the event loop and off
        the LLM pool. On timeout the worker thread keeps running (it cannot be
        cancelled) but the run is released instead of waiting forever.
        """
        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(
                    _tool_executor,
                    lambda: tool_exec.execute(
                        project_id=project_id,
                        chat_id=chat_id,
                        agent_id=agent_id,
                        tool_id=tool_id,
                        tool_parameters=tool_args,
                        # All five SYSTEM_VARIABLES are handed over here; this
                        # is the only place that fills them in.
                        user_id=user_id,
                        call_depth=self.call_depth,
                    ),
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Tool %s timed out after %ss", tool_id, timeout)
            return (
                "Cannot execute tool because it did not finish within "
                f"{timeout} seconds"
            )
        except Exception as exc:
            # ToolExec answers its own guards with a string so the model can
            # correct itself. Authoring errors (invalid description JSON, a body
            # without the declared function) used to escape here and abort the
            # whole run, so keep this path non-fatal too.
            logger.exception("Tool %s failed to run", tool_id)
            return f"Cannot execute tool because it failed to load or run: {exc}"

    @staticmethod
    def _stringify_tool_result(result: Any) -> str:
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, ensure_ascii=False)
        except TypeError:
            return str(result)

    @classmethod
    def _tool_result_text(cls, result: Any, *, pretty: bool = False) -> str:
        """Tool output cut to the cap that applies to its reader.

        The model gets the compact form cut at MAX_TOOL_RESULT_CHARS, so
        truncation keeps as much data as possible. The audit message under a
        tool call passes pretty=True, is read by a person, and keeps up to
        MAX_TOOL_AUDIT_CHARS instead.

        Pretty printing is skipped once the compact form is already over the
        audit cap. Indenting it and re-parsing every JSON-ish string inside it
        (see `_expand_json_strings`) costs real time on a large body -
        measured at ~43ms for a 5MB API response - and every character past
        the cap is discarded anyway, so a body that large is cut in its
        compact form.
        """
        limit = MAX_TOOL_AUDIT_CHARS if pretty else MAX_TOOL_RESULT_CHARS
        compact = cls._stringify_tool_result(result)
        if pretty and len(compact) <= MAX_TOOL_AUDIT_CHARS:
            return cls._truncate(cls._pretty_result(result), limit)
        return cls._truncate(compact, limit)

    @staticmethod
    def _truncate(text: str, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
        if len(text) <= limit:
            return text
        return (
            text[:limit]
            + f"\n...[truncated {len(text) - limit} characters]"
        )

    @classmethod
    def _fit_model_text(cls, result: Any, compact: Optional[str] = None) -> str:
        """The result as the model is handed it, trimmed inside the JSON.

        A plain cut lands mid-structure, and a model holding half a JSON object
        cannot tell what it is missing: it calls the tool again with different
        arguments and spends its rounds hunting instead of answering. A body
        over the cap is therefore trimmed by dropping items from its largest
        list, and failing that by cutting its longest string, so what arrives
        stays valid JSON that says how much of itself it is not showing. Only
        a body that cannot be trimmed that way falls back to the hard cut.
        """
        text = compact if compact is not None else cls._stringify_tool_result(result)
        if len(text) <= MAX_TOOL_RESULT_CHARS:
            return text
        trimmed = cls._trim_to_fit(result, MAX_TOOL_RESULT_CHARS)
        text = cls._stringify_tool_result(trimmed)
        if len(text) <= MAX_TOOL_RESULT_CHARS:
            return text
        return cls._truncate(text, MAX_TOOL_RESULT_CHARS)

    @classmethod
    def _trim_to_fit(cls, result: Any, limit: int) -> Any:
        """A copy of `result` with its lists and long strings shortened.

        The caller's value is never mutated: the audit card is built from the
        original result and must keep everything the tool returned.
        """
        for _ in range(MAX_TOOL_TRIM_ROUNDS):
            text = cls._stringify_tool_result(result)
            if len(text) <= limit:
                break
            shrunk = cls._shrink_once(result, len(text) - limit)
            if shrunk is None:
                break
            result = shrunk
        return result

    @classmethod
    def _shrink_once(cls, value: Any, over: int) -> Any:
        """Drop items from the largest list, or cut the longest string."""
        path = cls._largest_list_path(value)
        items = cls._at(value, path) if path is not None else None
        # Emptying a list that holds a single value throws that value away
        # whole, which is worse than cutting the long string inside it, so
        # that case falls through to the string branch below.
        if items is not None and len(items) > 1:
            size = len(cls._stringify_tool_result(items))
            average = max(1, size // max(1, len(items)))
            drop = max(1, min(len(items), over // average + 1))
            # The drop comes out of the middle rather than the end. A list
            # handed to the model is either a chronological log, where the
            # newest entries are the ones being asked about, or a ranked
            # result, where the top ones are; cutting one end loses exactly
            # the part that matters and sends the model hunting for it again.
            keep = len(items) - drop
            head = (keep + 1) // 2
            tail = keep - head
            trimmed = list(items[:head])
            trimmed.append({
                TOOL_TRIM_MARKER: (
                    f"{drop} of {len(items)} items omitted to fit the tool "
                    f"response limit; narrow the query or page further"
                ),
            })
            if tail:
                trimmed.extend(items[len(items) - tail:])
            return cls._replaced(value, path, trimmed)
        path = cls._longest_string_path(value)
        if path is not None:
            text = cls._at(value, path)
            keep = max(0, len(text) - over - 40)
            cut = text[:keep] + f"...[+{len(text) - keep} characters omitted]"
            return cls._replaced(value, path, cut)
        return None

    @classmethod
    def _largest_list_path(cls, value: Any) -> Optional[list]:
        """Path to the list holding the most items, if there is one."""
        best: Optional[list] = None
        best_len = 0
        for path, items in cls._walks(value):
            if len(items) > best_len:
                best, best_len = path, len(items)
        return best

    @classmethod
    def _longest_string_path(cls, value: Any) -> Optional[list]:
        """Path to the longest string, if it is worth cutting at all."""
        best: Optional[list] = None
        best_len = 0
        for path, text in cls._walks(value, strings=True):
            if len(text) > best_len:
                best, best_len = path, len(text)
        return best if best_len > 80 else None

    @classmethod
    def _walks(cls, value: Any, path: Optional[list] = None, depth: int = 0, strings: bool = False):
        """Yield (path, list) for lists, or (path, str) for strings."""
        if path is None:
            path = []
        if depth > _MAX_TOOL_TRIM_DEPTH:
            return
        if isinstance(value, str):
            if strings:
                yield path, value
            return
        if isinstance(value, list):
            if value and not strings:
                yield path, value
            for index, item in enumerate(value):
                yield from cls._walks(item, path + [index], depth + 1, strings)
            return
        if isinstance(value, dict):
            for key, item in value.items():
                yield from cls._walks(item, path + [key], depth + 1, strings)

    @staticmethod
    def _at(value: Any, path: list) -> Any:
        for key in path:
            value = value[key]
        return value

    @staticmethod
    def _replaced(value: Any, path: list, leaf: Any) -> Any:
        """A copy of `value` with `path` pointing at `leaf`, copy on write."""
        if not path:
            return leaf
        head, rest = path[0], path[1:]
        if isinstance(value, dict):
            copied = dict(value)
        elif isinstance(value, list):
            copied = list(value)
        else:
            return leaf
        copied[head] = AgentLoop._replaced(value[head], rest, leaf)
        return copied

    @classmethod
    def _tool_texts(cls, result: Any) -> tuple[str, str]:
        """(text for the model, text for the audit card) from one serialisation.

        The two differ: the model gets the compact form so truncation keeps as
        much data as possible, and the audit card the pretty one because a
        human reads that. The card keeps far more of the result than the model
        is handed - it is the record of what the tool actually returned - so
        the two are only shared once the body is too large for the card too.
        """
        compact = cls._stringify_tool_result(result)
        model_text = cls._fit_model_text(result, compact)
        if len(compact) <= MAX_TOOL_AUDIT_CHARS:
            return model_text, cls._truncate(
                cls._pretty_result(result), MAX_TOOL_AUDIT_CHARS
            )
        return model_text, cls._truncate(compact, MAX_TOOL_AUDIT_CHARS)

    @classmethod
    def _format_tool_output(
        cls,
        tool_name: Optional[str],
        tool_args: Any,
        result: Any,
        *,
        output: Optional[str] = None,
    ) -> str:
        """The audit card stored under one tool call.

        `output` is the finished, already-truncated output text. Callers that
        have it (see `_tool_texts`) pass it in so the result is not serialised a
        second time: on a multi-megabyte response that second dump is tens of
        milliseconds of blocked event loop for every tool call in a batch.
        """
        text = cls._tool_result_text(result, pretty=True) if output is None else output
        return (
            f"### Tool call: `{tool_name or 'Unknown'}`\n\n"
            "**Input**\n"
            "```json\n"
            f"{cls._json_block(tool_args)}\n"
            "```\n\n"
            "**Output**\n"
            "```text\n"
            f"{text}\n"
            "```"
        )

    @staticmethod
    def _json_block(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except TypeError:
            return json.dumps(str(value), ensure_ascii=False, indent=2)

    @staticmethod
    def _parse_json_text(text: str) -> Any:
        """The parsed value when `text` holds a JSON object or array, else None."""
        candidate = text.strip()
        if not candidate or candidate[0] not in "[{":
            return None
        try:
            return json.loads(candidate)
        except ValueError:
            return None

    @classmethod
    def _expand_json_strings(cls, value: Any, depth: int = 0) -> Any:
        """Display only: string fields that hold JSON are parsed so they indent too.

        `api_caller` answers with `{"status_code": 200, "content": "<body>"}`
        and the body is itself JSON. Dumped verbatim the body stayed a single
        escaped line, which is what made the Output block unreadable next to
        the pretty-printed Input block.
        """
        if depth >= 4:
            return value
        if isinstance(value, str):
            parsed = cls._parse_json_text(value)
            return value if parsed is None else cls._expand_json_strings(parsed, depth + 1)
        if isinstance(value, dict):
            return {key: cls._expand_json_strings(item, depth + 1) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._expand_json_strings(item, depth + 1) for item in value]
        return value

    @classmethod
    def _pretty_result(cls, result: Any) -> str:
        if isinstance(result, str):
            parsed = cls._parse_json_text(result)
            if parsed is None:
                return result
            result = parsed
        try:
            return json.dumps(cls._expand_json_strings(result), ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(result)

    @staticmethod
    def _message_text(response: Any) -> str:
        """Flatten a model reply to trimmed text.

        `content` is usually a string, but block-style replies arrive as a list;
        the sentinel check and the DB column both need a plain string.
        """
        content = getattr(response, "content", response)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = [
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            ]
            return "".join(parts).strip()
        return str(content).strip()

    @staticmethod
    def _combine_outputs(outputs: list[dict], original_input: str) -> str:
        if not outputs:
            return original_input
        # A failed agent must not read as a normal answer to the agents
        # downstream, so its error text is labelled as a failure.
        parts = [
            "[{name} #{index}]{marker}: {content}".format(
                name=o["agent_name"],
                index=o["index"],
                marker=" (FAILED)" if o.get("failed") else "",
                content=o["content"],
            )
            for o in outputs
        ]
        return (
            f"User message: {original_input}\n\nAgent responses:\n"
            + "\n\n".join(parts)
        )

    @staticmethod
    def _last_agent_message(
        db: Session, chat_id: int, agent_id: int
    ) -> Optional[str]:
        """Return the last answer this agent gave in this chat, if any."""
        row = (
            db.query(Message.content)
            .filter(
                Message.chat_id == chat_id,
                # An agent's reply carries its agent id in sender_id. Tool cards
                # carry the tool id there and user messages their user id, and
                # those id spaces are independent, so the sender kind is pinned
                # too rather than trusting the id on its own. Flow messages (one
                # agent's input being handed to the next) are excluded by their
                # message_type, so this only ever returns something the agent
                # itself said.
                Message.sender_id == agent_id,
                # Message.sender_type.notin_(("tool", "user")),
                # Message.message_type == "text",
                Message.content.isnot(None),
            )
            .order_by(Message.id.desc())
            .first()
        )
        content = row[0] if row else None
        return content or None

    @staticmethod
    def _tail(text: str, limit: int) -> str:
        """Return `text`, trimmed from the front to fit `limit` characters."""
        if len(text) <= limit:
            return text
        dropped = len(text) - limit
        return f"[...{dropped} earlier characters omitted]\n{text[-limit:]}"

    @staticmethod
    def _entity_name(db: Session, entity_type: Optional[str], entity_id: Optional[int]) -> Optional[str]:
        """Resolve a human-readable name for a polymorphic sender/receiver."""
        if not entity_id:
            return None
        if entity_type == "user":
            user = db.query(User).filter(User.id == entity_id).first()
            return user.name if user else None
        if entity_type in ("agent", "agents"):
            agent = db.query(Agent).filter(Agent.id == entity_id).first()
            return agent.name if agent else None
        if entity_type == "tool":
            tool = db.query(Tool).filter(Tool.id == entity_id).first()
            return tool.name if tool else None
        return None

    @staticmethod
    def _save_message(
        chat_id: int,
        sender_type: str,
        content: str,
        db: Session,
        sender_id: Optional[int] = None,
        receiver_type: Optional[str] = None,
        receiver_id: Optional[int] = None,
        message_type: str = "text",
        sender_name: Optional[str] = None,
        receiver_name: Optional[str] = None,
    ) -> Message:
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if chat is not None:
            receiver_type = receiver_type or "user"
            receiver_id = chat.user_id if receiver_id is None else receiver_id
        # Resolve human-readable names when the caller did not provide them.
        if sender_name is None:
            sender_name = AgentLoop._entity_name(db, sender_type, sender_id)
        if receiver_name is None:
            receiver_name = AgentLoop._entity_name(db, receiver_type, receiver_id)
        msg = Message(
            chat_id=chat_id,
            sender_type=sender_type,
            sender_id=sender_id,
            sender_name=sender_name,
            receiver_type=receiver_type,
            receiver_id=receiver_id,
            receiver_name=receiver_name,
            message_type=message_type,
            content=content,
        )
        db.add(msg)
        db.flush()
        if chat is not None:
            chat.last_message_id = msg.id
            chat.new_messages_count = db.query(Message).filter(Message.chat_id == chat_id).count()
        db.commit()
        db.refresh(msg)
        return msg

    async def _broadcast_message(self, msg: Message) -> None:
        out = MessageOut.model_validate(msg).model_dump(mode="json")
        await self.broadcast(msg.chat_id, {
            "type": "new_message",
            "message": out,
        })

    async def _stop_typing(self, chat_id: int, agent_label: str, active: bool) -> None:
        if not active:
            return
        await self.broadcast(chat_id, {
            "type": "stop_typing",
            "user_name": agent_label,
        })
