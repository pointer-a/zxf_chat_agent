from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.schemas import UserLoginResponse, UserCreate, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserLoginResponse)
async def login(body: UserCreate, db: AsyncSession = Depends(get_db)):
    """Login or register a user by name."""
    stmt = select(User).where(User.name == body.name)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    is_new = False
    if user is None:
        user = User(name=body.name, display_name=body.name)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        is_new = True

    return UserLoginResponse(
        user=UserResponse.model_validate(user),
        is_new=is_new,
        token=str(user.id),  # simple user ID token
    )


@router.get("/users/me", response_model=UserResponse)
async def get_current_user(
    user_id: int = 0,  # would come from auth middleware
    db: AsyncSession = Depends(get_db),
):
    """Placeholder: get current user. In production, use proper auth."""
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.model_validate(user)
