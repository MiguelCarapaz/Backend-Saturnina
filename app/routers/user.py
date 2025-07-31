from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.schemas.user import UserOut
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
import os
from dotenv import load_dotenv
from pydantic import EmailStr
from sqlalchemy.future import select

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "testsecret")
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

router = APIRouter()

def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="No autenticado")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")
    return email

@router.get("/profile", response_model=UserOut)
async def get_profile(current_email: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == current_email))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user

@router.put("/profile", response_model=UserOut)
async def update_profile(user_update: UserOut, current_email: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(User.__table__.select().where(User.email == current_email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user.name = user_update.name
    user.address = user_update.address
    user.phone = user_update.phone
    await db.commit()
    await db.refresh(user)
    return user

@router.post("/recover-password")
async def recover_password(email: EmailStr, db: AsyncSession = Depends(get_db)):
    result = await db.execute(User.__table__.select().where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    # Aquí deberías enviar un correo real con un token de recuperación
    return {"detail": "Se ha enviado un correo de recuperación (simulado)"}
