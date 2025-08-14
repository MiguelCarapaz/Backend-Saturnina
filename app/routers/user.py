from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, constr, EmailStr, validator, ValidationError
from sqlalchemy.future import select
from typing import Optional
import re
from app.database import get_db
from app.models.user import User
from .auth import get_current_user, get_password_hash, verify_password
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

# Routers
router = APIRouter(prefix="/user", tags=["users"])
router_public = APIRouter(tags=["users-public"])

# --- Pydantic models ---
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return user

# --- Perfil endpoints ---
@router.get("/{user_id}", response_model=dict)
async def get_user_profile(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado para acceder a este perfil")
    user = await get_user_by_id(db, user_id)
    return {"detail": {"nombre": user.name, "apellido": user.last_name, "telefono": user.phone, "email": user.email}}

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

# --- Password update implementation (soporta JSON y Form/MultiPart) ---
async def _update_password_impl(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Se aceptan:
      - application/json con keys current_password, new_password, confirm_password
      - form-data / x-www-form-urlencoded con las mismas keys o variantes (currentPassword, newPassword, confirmPassword, current, new, confirm)
    """
    # Normalizar y extraer datos desde JSON o form
    content_type = (request.headers.get("content-type") or "").lower()

    data = {
        "current_password": None,
        "new_password": None,
        "confirm_password": None
    }

    try:
        if "application/json" in content_type:
            payload = await request.json()
            data["current_password"] = payload.get("current_password") or payload.get("currentPassword") or payload.get("current")
            data["new_password"] = payload.get("new_password") or payload.get("newPassword") or payload.get("new")
            data["confirm_password"] = payload.get("confirm_password") or payload.get("confirmPassword") or payload.get("confirm")
        elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
            form = await request.form()
            data["current_password"] = form.get("current_password") or form.get("currentPassword") or form.get("current")
            data["new_password"] = form.get("new_password") or form.get("newPassword") or form.get("new")
            data["confirm_password"] = form.get("confirm_password") or form.get("confirmPassword") or form.get("confirm")
        else:
            # Intentamos parsear JSON por si acaso (clients sin content-type correcto)
            try:
                payload = await request.json()
                data["current_password"] = payload.get("current_password") or payload.get("currentPassword") or payload.get("current")
                data["new_password"] = payload.get("new_password") or payload.get("newPassword") or payload.get("new")
                data["confirm_password"] = payload.get("confirm_password") or payload.get("confirmPassword") or payload.get("confirm")
            except Exception:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Formato de petición no soportado o body vacío")

        # Validar con Pydantic para que reuna todas las reglas (incluye longitud y caracteres)
        try:
            pwd = PasswordUpdate(**data)
        except ValidationError as e:
            # devolvemos errores de validación con formato JSON
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=jsonable_encoder(e.errors()))

        # Verificar coincidencia de nuevas contraseñas (ya cubierta por Pydantic para estructura, pero confirm check lo hacemos)
        if pwd.new_password != pwd.confirm_password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Las nuevas contraseñas no coinciden")

        # Verificar que la nueva no sea igual a la actual
        # (verify_password espera contraseña plana y hash almacenado)
        if verify_password(pwd.new_password, current_user.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La nueva contraseña no puede ser igual a la actual")

        # Actualizar hash
        current_user.password_hash = get_password_hash(pwd.new_password)

        try:
            await db.commit()
            await db.refresh(current_user)
            return {"detail": {"message": "Contraseña actualizada correctamente", "user_id": str(current_user.id)}}
        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al actualizar la contraseña: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error inesperado: {str(e)}")

router.put("/update-password")(_update_password_impl)
router_public.put("/update-password")(_update_password_impl)

__all__ = ["router", "router_public"]
