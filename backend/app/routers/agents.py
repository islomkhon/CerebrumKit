import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.models.agent import Agent
from app.models.agent_context import AgentContextTool
from app.models.skill import Skill
from app.models.tool import Tool
from app.models.user import User
from app.schemas.schemas import (
    AgentContextToolIn,
    AgentCreate,
    AgentOut,
    SkillCreate,
    SkillOut,
    ToolCreate,
    ToolOut,
)

router = APIRouter(prefix="/admin", tags=["admin-agents"])

# Everything an agent payload reads, loaded in one round trip. `tools` feeds
# `tool_ids` and `context_tool_links` feeds `context_tools`; both are in the
# response, so leaving either lazy would fan out into a query per agent.
AGENT_LOAD_OPTIONS = (
    selectinload(Agent.skills),
    selectinload(Agent.tools),
    selectinload(Agent.context_tool_links).selectinload(AgentContextTool.tool),
)


def build_context_tool_links(
    skills: list[Skill], entries: list[AgentContextToolIn]
) -> list[AgentContextTool]:
    """Turn a payload's context tools into rows, refusing anything unusable.

    A tool only reaches an agent through a skill, so a context tool the agent
    does not have would fail inside the run and drop an error string into the
    system prompt on every message. Rejecting it here makes that a 400 the
    admin can act on instead.

    An inactive tool is accepted and kept: deactivating a tool is an ordinary
    admin action and must not make an unrelated edit to this agent fail. The
    run skips it (see AgentLoop._with_context_tools) and the UI marks it, so
    nothing about it is silent.
    """
    available = {}
    for skill in skills:
        for tool in skill.tools:
            available[tool.id] = tool

    links = []
    seen = set()
    for position, entry in enumerate(entries):
        if entry.tool_id in seen:
            raise HTTPException(
                status_code=400,
                detail=f"Tool {entry.tool_id} is selected more than once",
            )
        seen.add(entry.tool_id)

        tool = available.get(entry.tool_id)
        if tool is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Tool {entry.tool_id} is not provided by this agent's skills, "
                    "so it cannot be run before the message"
                ),
            )
        arguments = (entry.arguments or "").strip() or None
        if arguments is not None:
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Arguments for tool '{tool.name}' are not valid JSON: {exc}"
                    ),
                ) from exc
            if not isinstance(parsed, dict):
                raise HTTPException(
                    status_code=400,
                    detail=f"Arguments for tool '{tool.name}' must be a JSON object",
                )
            # Stored normalised, so the run has one shape to read.
            arguments = json.dumps(parsed)

        links.append(
            AgentContextTool(
                tool_id=tool.id,
                comment=(entry.comment or "").strip() or None,
                arguments=arguments,
                position=position,
            )
        )
    return links


def replace_context_tool_links(
    db: Session, agent: Agent, links: list[AgentContextTool]
) -> None:
    """Swap an agent's context tools for `links`.

    The clear is flushed before the refill on purpose. Replacing the whole
    collection in a single flush lets the unit of work emit the INSERT for a
    (agent, tool) pair before the DELETE of the row it is replacing, and the
    unique constraint behind that pair rejects it. Flushing in the middle
    forces the deletes out first.
    """
    agent.context_tool_links = []
    db.flush()
    agent.context_tool_links = links


def get_active_tools_or_404(db: Session, tool_ids: list[int]) -> list[Tool]:
    if not tool_ids:
        return []
    unique_tool_ids = set(tool_ids)
    tools = (
        db.query(Tool)
        .filter(Tool.id.in_(unique_tool_ids), Tool.is_active.is_(True))
        .all()
    )
    if len(tools) != len(unique_tool_ids):
        raise HTTPException(status_code=404, detail="Active tool not found")
    return tools


def get_active_skills_or_404(db: Session, skill_ids: list[int]) -> list[Skill]:
    if not skill_ids:
        return []
    unique_skill_ids = set(skill_ids)
    skills = (
        db.query(Skill)
        .filter(Skill.id.in_(unique_skill_ids), Skill.is_active.is_(True))
        .all()
    )
    if len(skills) != len(unique_skill_ids):
        raise HTTPException(status_code=404, detail="Active skill not found")
    return skills


@router.get("/agents", response_model=List[AgentOut])
def list_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    return (
        db.query(Agent)
        .options(*AGENT_LOAD_OPTIONS)
        .order_by(Agent.id.desc())
        .all()
    )


@router.post("/agents", response_model=AgentOut)
def create_agent(
    payload: AgentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    data = payload.model_dump()
    skill_ids = data.pop("skill_ids", [])
    data.pop("context_tools", None)
    skills = get_active_skills_or_404(db, skill_ids)
    agent = Agent(**data)
    agent.skills = skills
    db.add(agent)
    replace_context_tool_links(
        db,
        agent,
        build_context_tool_links(skills, payload.context_tools or []),
    )
    db.commit()
    return (
        db.query(Agent)
        .options(*AGENT_LOAD_OPTIONS)
        .filter(Agent.id == agent.id)
        .first()
    )


@router.get("/agents/{agent_id}", response_model=AgentOut)
def get_agent(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    agent = (
        db.query(Agent)
        .options(*AGENT_LOAD_OPTIONS)
        .filter(Agent.id == agent_id)
        .first()
    )
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/agents/{agent_id}", response_model=AgentOut)
def update_agent(
    agent_id: int,
    payload: AgentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    data = payload.model_dump()
    skill_ids = data.pop("skill_ids", [])
    data.pop("context_tools", None)
    skills = get_active_skills_or_404(db, skill_ids)
    for key, val in data.items():
        setattr(agent, key, val)
    agent.skills = skills
    # Omitted means "leave them alone"; an explicit list replaces them. See
    # AgentCreate.context_tools.
    if payload.context_tools is not None:
        replace_context_tool_links(
            db,
            agent,
            build_context_tool_links(skills, payload.context_tools),
        )
    db.commit()
    return (
        db.query(Agent)
        .options(*AGENT_LOAD_OPTIONS)
        .filter(Agent.id == agent.id)
        .first()
    )


@router.delete("/agents/{agent_id}")
def delete_agent(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(agent)
    db.commit()
    return {"ok": True}


@router.get("/agents/{agent_id}/skills", response_model=List[SkillOut])
def list_agent_skills(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    if not db.query(Agent).filter(Agent.id == agent_id).first():
        raise HTTPException(status_code=404, detail="Agent not found")
    return (
        db.query(Skill)
        .options(selectinload(Skill.tools))
        .join(Skill.agents)
        .filter(Agent.id == agent_id)
        .order_by(Skill.id.desc())
        .all()
    )


@router.get("/skills", response_model=List[SkillOut])
def list_skills(
    agent_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    query = db.query(Skill).options(selectinload(Skill.tools))
    if agent_id is not None:
        query = query.join(Skill.agents).filter(Agent.id == agent_id)
    return query.order_by(Skill.id.desc()).all()


@router.post("/skills", response_model=SkillOut)
def create_skill(
    payload: SkillCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    data = payload.model_dump()
    tool_ids = data.pop("tool_ids", [])
    tools = get_active_tools_or_404(db, tool_ids)
    skill = Skill(**data)
    skill.tools = tools
    db.add(skill)
    db.commit()
    return (
        db.query(Skill)
        .options(selectinload(Skill.tools))
        .filter(Skill.id == skill.id)
        .first()
    )


@router.put("/skills/{skill_id}", response_model=SkillOut)
def update_skill(
    skill_id: int,
    payload: SkillCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    data = payload.model_dump()
    tool_ids = data.pop("tool_ids", [])
    tools = get_active_tools_or_404(db, tool_ids)
    for key, val in data.items():
        setattr(skill, key, val)
    skill.tools = tools
    db.commit()
    return (
        db.query(Skill)
        .options(selectinload(Skill.tools))
        .filter(Skill.id == skill.id)
        .first()
    )


@router.delete("/skills/{skill_id}")
def delete_skill(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    db.delete(skill)
    db.commit()
    return {"ok": True}


@router.get("/tools", response_model=List[ToolOut])
def list_tools(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    return db.query(Tool).order_by(Tool.id.desc()).all()


@router.post("/tools", response_model=ToolOut)
def create_tool(
    payload: ToolCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    tool = Tool(**payload.model_dump())
    db.add(tool)
    db.commit()
    db.refresh(tool)
    return tool


@router.put("/tools/{tool_id}", response_model=ToolOut)
def update_tool(
    tool_id: int,
    payload: ToolCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    tool = db.query(Tool).filter(Tool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    for key, val in payload.model_dump().items():
        setattr(tool, key, val)
    db.commit()
    db.refresh(tool)
    return tool


@router.delete("/tools/{tool_id}")
def delete_tool(
    tool_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    tool = db.query(Tool).filter(Tool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    db.delete(tool)
    db.commit()
    return {"ok": True}
