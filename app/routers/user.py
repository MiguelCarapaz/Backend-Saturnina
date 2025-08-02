from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.future import select
from .auth import get_current_user

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(get_current_user)]
)

class UserProfile(BaseModel):
    name: str
    last_name: str
    email: str
    address: Optional[str] = None
    phone: Optional[str] = None
    role: str

@router.get("/me", response_model=UserProfile)
async def read_user_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return {
        "name": current_user.name,
        "last_name": current_user.last_name,
        "email": current_user.email,
        "address": current_user.address,
        "phone": current_user.phone,
        "role": current_user.role
    }

@router.put("/me", response_model=UserProfile)
async def update_user_me(
    user_data: UserProfile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    current_user.name = user_data.name
    current_user.last_name = user_data.last_name
    current_user.address = user_data.address
    current_user.phone = user_data.phone
    
    await db.commit()
    await db.refresh(current_user)
    
    return {
        "name": current_user.name,
        "last_name": current_user.last_name,
        "email": current_user.email,
        "address": current_user.address,
        "phone": current_user.phone,
        "role": current_user.role
    }