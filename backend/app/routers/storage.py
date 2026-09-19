import io
import json
import re
from datetime import date, datetime
from typing import Any, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from openpyxl import Workbook, load_workbook
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    Time,
    cast,
    func,
    inspect,
    or_,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import engine, get_db
from app.core.dependencies import get_current_user, require_admin as _require_admin
from app.models.project import Project
from app.models.project_table import ProjectTable
from app.models.user import User
from app.schemas.schemas import (
    ProjectSummaryOut,
    StorageColumnInfo,
    StorageRowOut,
    StorageRowPage,
    StorageRowPayload,
    StorageTableCreate,
    StorageTableInfo,
    StorageTableUpdate,
)

router = APIRouter(prefix="/admin/storage", tags=["admin-storage"])

# Internal / join tables that must not appear in the storage library.
_INTERNAL_TABLES = {
    "project_tables",
    "user_project",
    "agent_project",
    "agent_skill",
    "skill_tool",
}


# Tables owned by the application itself. They stay visible in the storage
# library but cannot be created/edited/deleted through the generic editor.
_SYSTEM_TABLES = {
    "users",
    "agents",
    "agent_context_tools",
    "skills",
    "tools",
    "chats",
    "messages",
    "projects",
    "countries",
    "memory",
    "platforms",
}

_RESERVED_COLUMNS = {"id", "created_at", "updated_at"}

# Upload / import limits, so a hostile or accidental file cannot exhaust memory.
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MiB
_MAX_IMPORT_ROWS = 20_000


def _excel_safe(value: Any) -> Any:
    """Neutralise spreadsheet formula injection on export.

    Excel treats text beginning with =, +, - or @ as a formula, so a stored
    value such as `=cmd|'/c calc'!A0` would execute when the export is opened.
    Prefixing an apostrophe keeps the value literal.
    """
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value

_ALLOWED_TYPES = {
    "integer",
    "bigInteger",
    "smallInteger",
    "tinyInteger",
    "string",
    "text",
    "longText",
    "mediumText",
    "boolean",
    "float",
    "double",
    "decimal",
    "date",
    "dateTime",
    "time",
    "timestamp",
    "json",
    "jsonb",
}

_IDENT_RE = re.compile(r"[^a-z0-9_]+")


def _slug(value: str, fallback: str = "") -> str:
    raw = value.strip().lower().replace("-", "_").replace(" ", "_")
    slug = _IDENT_RE.sub("", raw)
    if not slug or slug[0].isdigit():
        slug = fallback
    return slug[:48]


def _sql_type_name(data_type: str, length: int | None) -> str:
    if data_type == "bigInteger":
        return "BIGINT"
    if data_type == "smallInteger":
        return "SMALLINT"
    if data_type in {"integer", "tinyInteger"}:
        return "INTEGER"
    if data_type == "string":
        return f"VARCHAR({length or 255})"
    if data_type in {"text", "mediumText", "longText"}:
        return "TEXT"
    if data_type == "boolean":
        return "BOOLEAN"
    if data_type == "float":
        return "FLOAT"
    if data_type == "double":
        return "DOUBLE PRECISION"
    if data_type == "decimal":
        return "NUMERIC"
    if data_type == "date":
        return "DATE"
    if data_type in {"dateTime", "timestamp"}:
        return "TIMESTAMP WITH TIME ZONE"
    if data_type == "time":
        return "TIME"
    if data_type == "jsonb":
        return "JSONB"
    if data_type == "json":
        return "JSON"
    return "TEXT"


def _coerce_default(data_type: str, value: Any) -> Any:
    if value is None:
        return None
    if data_type in {"integer", "bigInteger", "smallInteger", "tinyInteger"}:
        return int(value)
    if data_type in {"float", "double", "decimal"}:
        return float(value)
    if data_type == "boolean":
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "on"}
    return value

def _ensure_required_columns(physical: Table, data: dict[str, Any], partial: bool = False) -> None:
    # Reject empty values for NOT NULL columns that have no database default.
    for column in physical.c:
        if column.name in {"id", "created_at", "updated_at"}:
            continue
        if column.nullable:
            continue
        if column.default is not None or column.server_default is not None:
            continue
        if partial and column.name not in data:
            continue
        value = data.get(column.name)
        if value is None or value == "":
            raise HTTPException(
                status_code=422,
                detail=f"Column '{column.name}' is required",
            )


def _clean_column_name(name: str) -> str:
    column = _slug(name, "")
    if not column:
        raise HTTPException(status_code=422, detail="Column name is required")
    if column in _RESERVED_COLUMNS:
        raise HTTPException(status_code=422, detail=f"'{column}' is reserved")
    return column


def _normalize_columns(columns: list) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    seen: set[str] = set()
    for column in columns:
        name = _clean_column_name(column.name)
        if name in seen:
            raise HTTPException(status_code=422, detail=f"Duplicate column: {name}")
        if column.data_type not in _ALLOWED_TYPES:
            raise HTTPException(status_code=422, detail=f"Unsupported column type: {column.data_type}")
        seen.add(name)
        clean.append(
            {
                "name": name,
                "data_type": column.data_type,
                "description": column.description if column.description not in (None, "") else None,
                "length": column.length,
                "nullable": column.nullable,
                "default_value": column.default_value if column.default_value != "" else None,
            }
        )
    return clean


def _server_default(column: Column) -> Any:
    server_default = column.server_default
    if server_default is None:
        return None
    arg = server_default.arg
    if isinstance(arg, str):
        if len(arg) >= 2 and arg[0] == "'" and arg[-1] == "'":
            return arg[1:-1]
        return arg
    return str(arg)


def _column_info(column: Column, comment: str | None = None) -> StorageColumnInfo:
    column_type = column.type
    editor_type: str = "string"
    length: int | None = None
    if isinstance(column_type, Integer):
        type_name = str(column_type).upper()
        if type_name == "BIGINT":
            editor_type = "bigInteger"
        elif type_name == "SMALLINT":
            editor_type = "smallInteger"
        else:
            editor_type = "integer"
    elif isinstance(column_type, String):
        editor_type = "string"
        length = column_type.length
    elif isinstance(column_type, Text):
        editor_type = "text"
    elif isinstance(column_type, Boolean):
        editor_type = "boolean"
    elif isinstance(column_type, Float):
        type_name = str(column_type).upper()
        editor_type = "double" if type_name.startswith("DOUBLE") else "float"
    elif isinstance(column_type, Numeric):
        editor_type = "decimal"
    elif isinstance(column_type, Date):
        editor_type = "date"
    elif isinstance(column_type, DateTime):
        editor_type = "timestamp"
    elif isinstance(column_type, Time):
        editor_type = "time"
    elif isinstance(column_type, JSON):
        editor_type = "jsonb" if str(column_type).upper() == "JSONB" else "json"
    return StorageColumnInfo(
        name=column.name,
        data_type=str(column_type),
        description=comment,
        editor_type=editor_type,
        length=length,
        nullable=column.nullable,
        default_value=_server_default(column),
    )


def _comments_for(db: Session, table_name: str) -> tuple[str | None, dict[str, str | None]]:
    inspector = inspect(db.connection())
    table_comment: str | None = None
    try:
        table_comment = (inspector.get_table_comment(table_name) or {}).get("text")
    except Exception:
        table_comment = None
    column_comments: dict[str, str | None] = {}
    try:
        for column in inspector.get_columns(table_name):
            column_comments[column["name"]] = column.get("comment")
    except Exception:
        pass
    return table_comment, column_comments


def _table_info(db: Session, table_name: str) -> StorageTableInfo:
    physical = _reflect_table(table_name, db.connection())
    try:
        row_count = db.execute(select(func.count()).select_from(physical)).scalar() or 0
    except Exception:
        row_count = 0
    table_comment, column_comments = _comments_for(db, table_name)
    return StorageTableInfo(
        name=table_name,
        description=table_comment,
        columns=[_column_info(column, column_comments.get(column.name)) for column in physical.c],
        row_count=row_count,
        projects=_table_projects(db, table_name),
        is_system=table_name in _SYSTEM_TABLES,
    )


def _create_physical_table(
    db: Session,
    table_name: str,
    columns: list[dict[str, Any]],
    description: str | None = None,
) -> None:
    pieces = [
        '"id" SERIAL PRIMARY KEY',
        '"created_at" TIMESTAMP WITH TIME ZONE',
        '"updated_at" TIMESTAMP WITH TIME ZONE',
    ]
    params: dict[str, Any] = {}
    for index, column in enumerate(columns):
        piece = f'"{column["name"]}" {_sql_type_name(column["data_type"], column["length"])}'
        if not column["nullable"]:
            piece += " NOT NULL"
        if column["default_value"] is not None:
            param = f"default_{index}"
            params[param] = _coerce_default(column["data_type"], column["default_value"])
            piece += f" DEFAULT :{param}"
        pieces.append(piece)
    sql = "CREATE TABLE " + f'"{table_name}" (' + ", ".join(pieces) + ")"
    db.execute(text(sql), params)
    if description:
        db.execute(text(f'COMMENT ON TABLE "{table_name}" IS :comment'), {"comment": description})
    for column in columns:
        if column.get("description"):
            db.execute(
                text(f'COMMENT ON COLUMN "{table_name}"."{column["name"]}" IS :comment'),
                {"comment": column["description"]},
            )
    db.commit()


def _add_column(db: Session, table_name: str, column: dict[str, Any]) -> None:
    piece = f'"{column["name"]}" {_sql_type_name(column["data_type"], column["length"])}'
    params: dict[str, Any] = {}
    if not column["nullable"]:
        piece += " NOT NULL"
    if column["default_value"] is not None:
        piece += " DEFAULT :default"
        params["default"] = _coerce_default(column["data_type"], column["default_value"])
    try:
        db.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN {piece}'), params)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=f"Could not add column '{column['name']}': {exc}") from exc
    if column.get("description"):
        db.execute(
            text(f'COMMENT ON COLUMN "{table_name}"."{column["name"]}" IS :comment'),
            {"comment": column["description"]},
        )


def _alter_column(db: Session, table_name: str, column_name: str, desired: dict[str, Any]) -> None:
    physical = _reflect_table(table_name, db.connection())
    existing = physical.c[column_name]
    new_type = _sql_type_name(desired["data_type"], desired["length"])
    if str(existing.type).upper() != new_type:
        try:
            db.execute(
                text(
                    f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" TYPE {new_type} '
                    f'USING "{column_name}"::{new_type}'
                )
            )
        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=422,
                detail=f"Could not change column '{column_name}' type: {exc}",
            ) from exc
    if desired["nullable"]:
        db.execute(text(f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" DROP NOT NULL'))
    else:
        try:
            db.execute(text(f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" SET NOT NULL'))
        except Exception as exc:
            db.rollback()
            raise HTTPException(
                status_code=422,
                detail=f"Could not make column '{column_name}' NOT NULL: {exc}",
            ) from exc
    db.execute(text(f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" DROP DEFAULT'))
    if desired["default_value"] is not None:
        db.execute(
            text(f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" SET DEFAULT :default'),
            {"default": _coerce_default(desired["data_type"], desired["default_value"])},
        )
    if desired.get("description"):
        db.execute(
            text(f'COMMENT ON COLUMN "{table_name}"."{column_name}" IS :comment'),
            {"comment": desired["description"]},
        )
    else:
        db.execute(text(f'COMMENT ON COLUMN "{table_name}"."{column_name}" IS NULL'))


def _sync_columns(db: Session, table_name: str, desired: list[dict[str, Any]]) -> None:
    physical = _reflect_table(table_name, db.connection())
    existing = [column for column in physical.c if column.name not in _RESERVED_COLUMNS]
    existing_names = [column.name for column in existing]
    desired_names = [column["name"] for column in desired]

    renames: dict[str, str] = {}
    for existing_name, desired_name in zip(existing_names, desired_names):
        if (
            existing_name != desired_name
            and desired_names.count(desired_name) == 1
            and existing_names.count(existing_name) == 1
        ):
            renames[existing_name] = desired_name

    post_names = [renames.get(name, name) for name in existing_names]

    for old_name, new_name in renames.items():
        db.execute(text(f'ALTER TABLE "{table_name}" RENAME COLUMN "{old_name}" TO "{new_name}"'))

    desired_by_name = {column["name"]: column for column in desired}
    for column in existing:
        current_name = renames.get(column.name, column.name)
        if current_name not in desired_by_name:
            continue
        _alter_column(db, table_name, current_name, desired_by_name[current_name])

    for name in post_names:
        if name not in desired_names:
            db.execute(text(f'ALTER TABLE "{table_name}" DROP COLUMN "{name}"'))

    for column in desired:
        if column["name"] not in post_names:
            _add_column(db, table_name, column)

    db.commit()


def _ensure_editable(table_name: str) -> None:
    if not inspect(engine).has_table(table_name):
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")
    if table_name in _INTERNAL_TABLES or table_name in _SYSTEM_TABLES:
        raise HTTPException(status_code=400, detail=f"'{table_name}' is a system table and cannot be edited")


def _physical_table_names() -> list[str]:
    return sorted(
        name for name in inspect(engine).get_table_names() if name not in _INTERNAL_TABLES
    )


def _reflect_table(table_name: str, bind: Any | None = None) -> Table:
    connection = bind or engine
    if not inspect(connection).has_table(table_name):
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")
    metadata = MetaData()
    return Table(table_name, metadata, autoload_with=connection)


def _table_projects(db: Session, table_name: str) -> list[ProjectSummaryOut]:
    rows = (
        db.query(ProjectTable, Project)
        .join(Project, Project.id == ProjectTable.project_id)
        .filter(ProjectTable.table_name == table_name)
        .order_by(Project.id)
        .all()
    )
    return [ProjectSummaryOut(id=project.id, name=project.name) for _, project in rows]


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, (int, float, bool, str)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _coerce_value(value: Any, column: Column) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and value == "":
        return None
    column_type = column.type
    if isinstance(column_type, Integer):
        return int(value)
    if isinstance(column_type, (Float, Numeric)):
        return float(value)
    if isinstance(column_type, Boolean):
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "on"}
    if isinstance(column_type, JSON):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid JSON for column '{column.name}'",
                )
        return value
    return value


def _row_to_out(row: Any, physical: Table) -> StorageRowOut:
    mapping = row._mapping if hasattr(row, "_mapping") else row
    data: dict[str, Any] = {}
    created_at = None
    updated_at = None
    for column in physical.c:
        if column.name == "id":
            continue
        value = _json_safe(mapping.get(column.name))
        if column.name == "created_at":
            created_at = value
        elif column.name == "updated_at":
            updated_at = value
        else:
            data[column.name] = value
    return StorageRowOut(id=mapping["id"], data=data, created_at=created_at, updated_at=updated_at)


@router.get("/tables", response_model=List[StorageTableInfo])
def list_all_tables(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    result: list[StorageTableInfo] = []
    names = sorted(_physical_table_names(), key=lambda name: (name in _SYSTEM_TABLES, name))
    for name in names:
        try:
            physical = _reflect_table(name, db.connection())
        except HTTPException:
            continue
        try:
            row_count = db.execute(select(func.count()).select_from(physical)).scalar() or 0
        except Exception:
            row_count = 0
        table_comment, column_comments = _comments_for(db, name)
        columns = [_column_info(column, column_comments.get(column.name)) for column in physical.c]
        result.append(
            StorageTableInfo(
                name=name,
                description=table_comment,
                columns=columns,
                row_count=row_count,
                projects=_table_projects(db, name),
                is_system=name in _SYSTEM_TABLES,
            )
        )
    return result


@router.post("/tables", response_model=StorageTableInfo)
def create_table(
    payload: StorageTableCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    table_name = _slug(payload.name, "")
    if not table_name:
        raise HTTPException(status_code=422, detail="Table name is required")
    if table_name in _INTERNAL_TABLES or table_name in _SYSTEM_TABLES:
        raise HTTPException(status_code=422, detail=f"'{table_name}' is a reserved table name")
    if inspect(engine).has_table(table_name):
        raise HTTPException(status_code=409, detail=f"Table '{table_name}' already exists")
    columns = _normalize_columns(payload.columns)
    try:
        _create_physical_table(db, table_name, columns, payload.description)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=f"Could not create table: {exc}") from exc
    return _table_info(db, table_name)


@router.put("/tables/{table_name}", response_model=StorageTableInfo)
def update_table(
    table_name: str,
    payload: StorageTableUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    _ensure_editable(table_name)
    current_name = table_name
    new_name = _slug(payload.name, table_name) if payload.name else table_name
    if new_name != current_name:
        if new_name in _INTERNAL_TABLES or new_name in _SYSTEM_TABLES:
            raise HTTPException(status_code=422, detail=f"'{new_name}' is a reserved table name")
        if inspect(engine).has_table(new_name):
            raise HTTPException(status_code=409, detail=f"Table '{new_name}' already exists")
        db.execute(text(f'ALTER TABLE "{current_name}" RENAME TO "{new_name}"'))
        db.query(ProjectTable).filter(ProjectTable.table_name == current_name).update(
            {ProjectTable.table_name: new_name}
        )
        db.commit()
        current_name = new_name
    if payload.columns is not None:
        desired = _normalize_columns(payload.columns)
        try:
            _sync_columns(db, current_name, desired)
        except HTTPException:
            raise
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=422, detail=f"Could not update table: {exc}") from exc
    if payload.description is not None:
        if payload.description:
            db.execute(
                text(f'COMMENT ON TABLE "{current_name}" IS :comment'),
                {"comment": payload.description},
            )
        else:
            db.execute(text(f'COMMENT ON TABLE "{current_name}" IS NULL'))
        db.commit()
    return _table_info(db, current_name)


@router.delete("/tables/{table_name}")
def delete_table(
    table_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    _ensure_editable(table_name)
    db.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
    db.query(ProjectTable).filter(ProjectTable.table_name == table_name).delete()
    db.commit()
    return {"ok": True}


@router.get("/tables/{table_name}/rows", response_model=StorageRowPage)
def list_rows(
    table_name: str,
    search: str = "",
    page: int = 1,
    per_page: int | str = 50,
    sort_by: str = "id",
    sort_dir: str = "asc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    physical = _reflect_table(table_name, db.connection())
    if "id" not in physical.c:
        raise HTTPException(status_code=422, detail="Table has no 'id' column")

    query = select(physical)
    if search.strip():
        q = f"%{search.strip()}%"
        conditions = []
        for column in physical.c:
            if column.name == "id":
                continue
            try:
                conditions.append(cast(column, String).ilike(q))
            except Exception:
                pass
        if conditions:
            query = query.where(or_(*conditions))

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0
    if sort_by not in physical.c:
        raise HTTPException(status_code=422, detail=f"Unknown sort column: {sort_by}")
    order = physical.c[sort_by].desc() if sort_dir.lower() == "desc" else physical.c[sort_by].asc()
    if per_page == "all":
        rows = db.execute(query.order_by(order)).all()
        pages = 1
        per = total
    else:
        per = int(per_page)
        pages = max(1, (total + per - 1) // per) if total else 1
        rows = db.execute(query.order_by(order).offset((page - 1) * per).limit(per)).all()

    items = [_row_to_out(row, physical) for row in rows]
    return StorageRowPage(items=items, total=total, page=page, per_page=per_page, pages=pages)


@router.post("/tables/{table_name}/rows", response_model=StorageRowOut)
def create_row(
    table_name: str,
    payload: StorageRowPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    physical = _reflect_table(table_name, db.connection())
    if "id" not in physical.c:
        raise HTTPException(status_code=422, detail="Table has no 'id' column")
    data: dict[str, Any] = {}
    for name, value in payload.data.items():
        if name in physical.c and name not in {"id", "created_at", "updated_at"}:
            data[name] = _coerce_value(value, physical.c[name])
    _ensure_required_columns(physical, data)
    if "created_at" in physical.c:
        data["created_at"] = func.now()
    if "updated_at" in physical.c:
        data["updated_at"] = func.now()
    try:
        result = db.execute(physical.insert().values(**data))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Could not save row: {str(exc.orig).splitlines()[0]}",
        ) from exc
    row_id = result.inserted_primary_key[0]
    row = db.execute(select(physical).where(physical.c.id == row_id)).first()
    return _row_to_out(row, physical)


@router.put("/tables/{table_name}/rows/{row_id}", response_model=StorageRowOut)
def update_row(
    table_name: str,
    row_id: int,
    payload: StorageRowPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    physical = _reflect_table(table_name, db.connection())
    if "id" not in physical.c:
        raise HTTPException(status_code=422, detail="Table has no 'id' column")
    data: dict[str, Any] = {}
    for name, value in payload.data.items():
        if name in physical.c and name not in {"id", "created_at", "updated_at"}:
            data[name] = _coerce_value(value, physical.c[name])
    _ensure_required_columns(physical, data, partial=True)
    if "updated_at" in physical.c:
        data["updated_at"] = func.now()
    if data:
        try:
            db.execute(physical.update().where(physical.c.id == row_id).values(**data))
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"Could not save row: {str(exc.orig).splitlines()[0]}",
            ) from exc
    row = db.execute(select(physical).where(physical.c.id == row_id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Row not found")
    return _row_to_out(row, physical)


@router.delete("/tables/{table_name}/rows/{row_id}")
def delete_row(
    table_name: str,
    row_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    physical = _reflect_table(table_name, db.connection())
    if "id" not in physical.c:
        raise HTTPException(status_code=422, detail="Table has no 'id' column")
    db.execute(physical.delete().where(physical.c.id == row_id))
    db.commit()
    return {"ok": True}


async def _load_excel(file: UploadFile):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Please upload an .xlsx file")
    # Read in bounded chunks so an oversized (or zip-bomb style) upload cannot
    # pull unbounded data into memory.
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Excel file is too large (limit {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
            )
        chunks.append(chunk)
    content = b"".join(chunks)
    try:
        return load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid Excel file: {exc}") from exc


def _excel_headers_and_rows(workbook, sample_size: int = 5) -> tuple[list[str], list[list[Any]], Any]:
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    try:
        headers = [str(value).strip() if value is not None else "" for value in next(rows)]
    except StopIteration:
        return [], [], iter(())

    samples: list[list[Any]] = []
    for index, row in enumerate(rows):
        if index < sample_size:
            samples.append([value for value in row[: len(headers)]])

    return headers, samples, sheet.iter_rows(min_row=2, values_only=True)


@router.post("/tables/{table_name}/preview-excel")
async def preview_excel(
    table_name: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    physical = _reflect_table(table_name, db.connection())
    workbook = await _load_excel(file)
    headers, samples, _ = _excel_headers_and_rows(workbook)
    normalized_headers = {header.strip().lower(): header for header in headers if header}
    suggested_mapping = {
        column.name: normalized_headers.get(column.name.lower(), "")
        for column in physical.c
        if column.name != "id"
    }
    return {
        "headers": headers,
        "sample_rows": samples,
        "database_columns": [
            {
                "name": column.name,
                "description": None,
                "data_type": str(column.type),
                "nullable": column.nullable,
            }
            for column in physical.c
            if column.name != "id"
        ],
        "suggested_mapping": suggested_mapping,
    }


@router.post("/tables/{table_name}/import-excel")
async def import_excel(
    table_name: str,
    file: UploadFile = File(...),
    mapping: str = Form("{}"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    physical = _reflect_table(table_name, db.connection())
    try:
        column_mapping = json.loads(mapping or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Invalid column mapping") from exc
    if not isinstance(column_mapping, dict):
        raise HTTPException(status_code=422, detail="Invalid column mapping")
    column_mapping = {
        str(db_column): str(excel_column)
        for db_column, excel_column in column_mapping.items()
        if db_column and excel_column
    }

    workbook = await _load_excel(file)
    headers, _, rows = _excel_headers_and_rows(workbook, sample_size=0)
    if not headers:
        return {"imported": 0}

    imported = 0
    processed = 0
    for row in rows:
        processed += 1
        if processed > _MAX_IMPORT_ROWS:
            # Nothing is committed yet, so raising here discards the whole import.
            raise HTTPException(
                status_code=413,
                detail=f"Import is limited to {_MAX_IMPORT_ROWS} rows per file",
            )
        row_map = {
            headers[index]: value
            for index, value in enumerate(row)
            if index < len(headers) and headers[index]
        }
        filtered = {}
        for db_column, excel_column in column_mapping.items():
            if db_column in physical.c and excel_column in row_map and row_map[excel_column] is not None:
                filtered[db_column] = _coerce_value(row_map[excel_column], physical.c[db_column])
        if not filtered:
            continue
        if "created_at" in physical.c:
            filtered.setdefault("created_at", func.now())
        if "updated_at" in physical.c:
            filtered.setdefault("updated_at", func.now())
        db.execute(physical.insert().values(**filtered))
        imported += 1
    db.commit()
    return {"imported": imported}


@router.get("/tables/{table_name}/export-excel")
def export_excel(
    table_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    physical = _reflect_table(table_name, db.connection())
    headers = list(physical.c.keys())
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    sheet.append(headers)
    for row in db.execute(select(physical).order_by(physical.c["id"])).all():
        mapping = row._mapping if hasattr(row, "_mapping") else row
        sheet.append([_excel_safe(_json_safe(mapping.get(header))) for header in headers])
    output = io.BytesIO()
    workbook.save(output)
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{table_name}.xlsx"'},
    )
