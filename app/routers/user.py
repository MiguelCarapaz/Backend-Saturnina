from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, constr, EmailStr, validator
from sqlalchemy.future import select
from typing import Optional
import re
from app.database import get_db
from app.models.user import User
from .auth import get_current_user, get_password_hash, verify_password

router = APIRouter(
    prefix="/user",
    tags=["users"],
    dependencies=[Depends(get_current_user)]
)

# --- Modelos Pydantic ---
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
    current_password: str
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

# --- Helpers ---
async def get_user_by_id(db: AsyncSession, user_id: int) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )
    return user

# --- Endpoints ---
@router.get("/{user_id}", response_model=dict)
async def get_user_profile(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Obtiene el perfil del usuario autenticado.
    """
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No autorizado para acceder a este perfil"
        )

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
    """
    Actualiza el perfil del usuario autenticado.
    """
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No autorizado para actualizar este perfil"
        )

    user = await get_user_by_id(db, user_id)

    # Verificar si el email ya existe (excepto para el usuario actual)
    if user_data.email != user.email:
        existing_email = await db.execute(
            select(User).where(User.email == user_data.email)
        )
        if existing_email.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El email ya está en uso por otro usuario"
            )

    # Actualizar campos
    user.name = user_data.nombre
    user.last_name = user_data.apellido
    user.phone = user_data.telefono
    user.email = user_data.email

    try:
        await db.commit()
        await db.refresh(user)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar el perfil: {str(e)}"
        )

    return {"message": "Perfil actualizado correctamente"}

@router.put("/update-password")
async def update_password(
    password_data: PasswordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Verificar coincidencia de nuevas contraseñas
    if password_data.new_password != password_data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las nuevas contraseñas no coinciden"
        )

    # Verificar que la nueva no sea igual a la actual
    if verify_password(password_data.new_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La nueva contraseña no puede ser igual a la actual"
        )

    # Actualizar contraseña
    current_user.password_hash = get_password_hash(password_data.new_password)
    
    try:
        await db.commit()
        return {
            "detail": {
                "message": "Contraseña actualizada correctamente",
                "user_id": str(current_user.id)
            }
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar la contraseña: {str(e)}"
        )
    