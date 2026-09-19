from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_admin
from app.core.rate_limit import login_rate_limit, register_rate_limit
from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User
from app.schemas.auth import LoginRequest, Token, UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserOut,
    dependencies=[Depends(register_rate_limit)],
)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    """Public self-registration. Always creates a client account.

    The role is intentionally NOT taken from the request body: allowing it let
    anyone mint an admin account. Elevated roles are only granted through the
    admin-authenticated /admin/users endpoints.
    """
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        name=payload.name,
        email=payload.email,
        password=hash_password(payload.password),
        role="client",
        country_id=payload.country_id,
        language=payload.language,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List all users. Admin only - this endpoint used to be fully public."""
    return db.query(User).order_by(User.id.asc()).all()


@router.post("/login", response_model=Token, dependencies=[Depends(login_rate_limit)])
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is disabled")
    access_token = create_access_token(data={"sub": str(user.id), "role": user.role})
    return Token(access_token=access_token, user=UserOut.model_validate(user))
