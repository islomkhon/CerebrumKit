import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek
from pydantic import BaseModel, Field

from app.core.dependencies import get_current_user, require_admin
from app.core.llm import build_chat_model, resolve_config
from app.core.tool_exec import SYSTEM_VARIABLES
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin-generator"])


class GeneratorRequest(BaseModel):
    description: str = Field(..., min_length=1)
    structure: dict[str, Any] = Field(default_factory=dict)


def get_llm() -> ChatDeepSeek:
    """The generator's client, built from the system's active connection.

    A wrong temperature or max_tokens on the row is intentional here: the panel
    is where those are set, so the generator honours them like every other call.
    """
    config = resolve_config()
    if not config.api_key and not config.base_url:
        raise HTTPException(
            status_code=500,
            detail="No LLM connection is configured. Add one in Settings.",
        )
    return build_chat_model(
        config,
        temperature=0.1,
        timeout=120,
        model_kwargs={"response_format": {"type": "json_object"}},
        max_tokens=4096,
    )


def extract_json(content: str) -> Any:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    starts = [idx for idx in (text.find("{"), text.find("[")) if idx != -1]
    if not starts:
        raise HTTPException(status_code=502, detail="Generator did not return JSON")

    start = min(starts)
    decoder = json.JSONDecoder()
    try:
        parsed, _ = decoder.raw_decode(text[start:])
        return parsed
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Generator returned invalid JSON") from exc


# Only tool structures carry a `body`, and that body is Python this app executes
# itself, so it starts with the run's ids already in scope (see
# app.core.tool_exec.SYSTEM_VARIABLES). The generator has to know that, or it
# writes `project_id` into the tool's `parameters` and asks the model to supply a
# value the server overwrites anyway.
TOOL_BODY_SYSTEM_VARIABLES = (
    "If the resource is a tool whose body is Python, that body already runs with "
    "the following variables in scope, supplied by the server on every call: "
    + ", ".join(f"{name} ({description})" for name, description in SYSTEM_VARIABLES.items())
    + ". Never declare them as function parameters, never list them under the tool "
    "definition\'s parameters, and never expect the model to pass them. Use them to "
    "scope the body to the run it belongs to - for example filter rows by "
    "project_id instead of looking the project up by name."
)


@router.post("/generator")
def generate_json(
    payload: GeneratorRequest,
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    llm = get_llm()
    structure = payload.structure or {"name": "", "description": "", "type": "", "body": "", "is_active": True}
    instructions = (
        "The user will provide some description about a resource you need to create."
        "Convert the user's description into useful, well-structured JSON. Return only valid JSON. Do not include markdown, "
        "comments, explanations, or surrounding text. The top-level value must be a JSON object. Use exactly the keys from the provided JSON structure. "
        "Do not add extra keys. Preserve boolean fields as booleans."
    )
    if "body" in structure:
        instructions = f"{instructions}\n\n{TOOL_BODY_SYSTEM_VARIABLES}"
    response = llm.invoke([
        SystemMessage(content=(
            f"{instructions}\n\n"
            f"JSON structure to fill: \n{json.dumps(structure, ensure_ascii=False)}"
        )),
        HumanMessage(content=payload.description),
    ])
    return extract_json(str(response.content))
