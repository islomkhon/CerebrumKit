"""
Admin users CRUD router.
Only admin users can access these endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_admin as _require_admin
from app.core.security import hash_password
from app.models.user import User
from app.schemas.auth import UserCreate, UserOut

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """List all users in the system."""
    return db.query(User).order_by(User.id.asc()).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """Create a new user."""
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        name=payload.name,
        email=payload.email,
        password=hash_password(payload.password),
        role=payload.role,
        country_id=payload.country_id,
        language=payload.language,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """Get a single user by ID."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """Update a user's details."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check email uniqueness (excluding this user)
    email_exists = (
        db.query(User)
        .filter(User.email == payload.email, User.id != user_id)
        .first()
    )
    if email_exists:
        raise HTTPException(status_code=400, detail="Email already in use by another user")

    user.name = payload.name
    user.email = payload.email
    user.role = payload.role
    user.country_id = payload.country_id
    user.language = payload.language

    # Only update password if a non-empty one is provided
    if payload.password:
        user.password = hash_password(payload.password)

    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """Delete a user (soft-delete by setting is_active=False, or hard-delete)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()
