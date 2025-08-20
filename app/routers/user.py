from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel, constr, EmailStr, validator, ValidationError
from typing import Optional, Dict, Any
import re
from datetime import datetime

from app.database import get_db
from app.models.user import User
from .auth import get_current_user, get_password_hash, verify_password

router = APIRouter(
    prefix="/user",
    dependencies=[Depends(get_current_user)]
)


router_public = APIRouter()

class UserProfileResponse(BaseModel):
    nombre: str
    apellido: str
    telefono: Optional[str]
    email: EmailStr

class UserUpdateRequest(BaseModel):
    nombre: constr(min_length=3, max_length=50)
    apellido: constr(min_length=3, max_length=50)
    telefono: constr(pattern=r'^[0-9]{10}$')
    email: EmailStr

class PasswordUpdate(BaseModel):
    current_password: Optional[str] = None
    new_password: str
    confirm_password: str

    @validator('new_password')
    def validate_password(cls, v):
        if len(v) < 9 or len(v) > 18:
            raise ValueError('La contraseña debe tener entre 9 y 18 caracteres')
        if not re.search(r'[A-Z]', v):
            raise ValueError('La contraseña debe contener al menos una mayúscula')
        if not re.search(r'\d', v):
            raise ValueError('La contraseña debe contener al menos un número')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('La contraseña debe contener al menos un carácter especial')
        return v

async def get_user_by_id(db: AsyncSession, user_id: int) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    return user

def normalize_password_payload(payload: Dict[str, Any]) -> Dict[str, Optional[str]]:
    mapped = {
        "current_password": None,
        "new_password": None,
        "confirm_password": None
    }

    current_keys = ["current_password", "currentPassword", "current"]
    new_keys = ["new_password", "newPassword", "new", "password"]
    confirm_keys = ["confirm_password", "confirmPassword", "confirm", "check_password", "checkPassword", "check"]

    for k in current_keys:
        if k in payload and payload.get(k) is not None:
            mapped["current_password"] = payload.get(k)
            break

    for k in new_keys:
        if k in payload and payload.get(k) is not None:
            mapped["new_password"] = payload.get(k)
            break

    for k in confirm_keys:
        if k in payload and payload.get(k) is not None:
            mapped["confirm_password"] = payload.get(k)
            break

    return mapped

async def _process_password_update(payload: Dict[str, Any], db: AsyncSession, current_user: User):
    data = normalize_password_payload(payload)

    try:
        pwd = PasswordUpdate(**data)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.errors())

    if pwd.new_password != pwd.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Las nuevas contraseñas no coinciden")

    if verify_password(pwd.new_password, current_user.password_hash):
        raise HTTPException(status_code=406, detail="La nueva contraseña no puede ser igual a la actual")

    current_user.password_hash = get_password_hash(pwd.new_password)

    try:
        await db.commit()
        await db.refresh(current_user)
        return JSONResponse(status_code=200, content={"detail": {"message": "Contraseña actualizada correctamente", "user_id": str(current_user.id)}})
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al actualizar la contraseña: {str(e)}")


@router.get("/{user_id}", response_model=dict)
async def get_user_profile(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado para acceder a este perfil")
    user = await get_user_by_id(db, user_id)
    return {
        "detail": {
            "nombre": user.name,
            "apellido": user.last_name,
            "telefono": user.phone,
            "email": user.email
        }
    }

@router.put("/{user_id}", response_model=dict)
async def update_user_profile(
    user_id: int,
    user_data: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado para actualizar este perfil")

    user = await get_user_by_id(db, user_id)

    if user_data.email != user.email:
        existing_email = await db.execute(select(User).where(User.email == user_data.email))
        if existing_email.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El email ya está en uso por otro usuario")

    user.name = user_data.nombre
    user.last_name = user_data.apellido
    user.phone = user_data.telefono
    user.email = user_data.email

    try:
        await db.commit()
        await db.refresh(user)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al actualizar el perfil: {str(e)}")

    return {"message": "Perfil actualizado correctamente"}

@router.put("/update-password")
async def update_password_user_prefix(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    content_type = (request.headers.get("content-type") or "").lower()
    payload = {}
    if "application/json" in content_type:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
    else:
        try:
            form = await request.form()
            payload = dict(form)
        except Exception:
            try:
                payload = await request.json()
            except Exception:
                payload = {}

    return await _process_password_update(payload, db, current_user)

@router_public.put("/update-password")
async def update_password_public(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    content_type = (request.headers.get("content-type") or "").lower()
    payload = {}
    if "application/json" in content_type:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
    else:
        try:
            form = await request.form()
            payload = dict(form)
        except Exception:
            try:
                payload = await request.json()
            except Exception:
                payload = {}

    return await _process_password_update(payload, db, current_user)
