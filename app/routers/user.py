from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, constr
from sqlalchemy.future import select

from app.database import get_db
from app.models.user import User
from .auth import get_current_user, get_password_hash, verify_password

router = APIRouter(
    prefix="/user",
    tags=["users"],
    dependencies=[Depends(get_current_user)]
)

# Pydantic model for updating user profile data, matching frontend fields
class UserUpdate(BaseModel):
    nombre: constr(min_length=3, max_length=10)
    apellido: constr(min_length=3, max_length=10)
    telefono: constr(pattern=r'^[0-9]{10}$')
    email: str

# Pydantic model for updating password
class PasswordUpdate(BaseModel):
    new_password: str
    check_password: str

@router.get("/{user_id}")
async def get_user_profile(
    user_id: int, 
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Obtiene el perfil de un usuario.
    Un usuario solo puede ver su propio perfil.
    """
    # Verificar que el usuario logueado está solicitando su propio perfil
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No autorizado para acceder a este perfil"
        )

    # Obtener el usuario de la base de datos para asegurarnos de tener los datos actualizados
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    # Formato de respuesta que espera el frontend
    return {
        "detail": {
            "nombre": user.name,
            "apellido": user.last_name,
            "telefono": user.phone,
            "email": user.email
        }
    }

@router.put("/{user_id}")
async def update_user_profile(
    user_id: int, 
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Actualiza el perfil de un usuario.
    Un usuario solo puede actualizar su propio perfil.
    """
    # Verificar que el usuario logueado está actualizando su propio perfil
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No autorizado para actualizar este perfil"
        )

    # Obtener el usuario de la base de datos
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado"
        )

    # Actualizar los campos del usuario
    user.name = user_data.nombre
    user.last_name = user_data.apellido
    user.phone = user_data.telefono
    # Nota: No actualizamos el email aquí por seguridad

    try:
        await db.commit()
        await db.refresh(user)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al actualizar el perfil: {str(e)}"
        )

    return {"message": "Perfil actualizado correctamente"}

@router.put("/update-password")
async def update_password(
    password_data: PasswordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Actualiza la contraseña del usuario actual.
    """
    # Verificar que las contraseñas coincidan
    if password_data.new_password != password_data.check_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Las contraseñas no coinciden"
        )

    # Verificar que la nueva contraseña no sea igual a la anterior
    if verify_password(password_data.new_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail="La nueva contraseña no puede ser igual a la anterior"
        )

    # Actualizar la contraseña
    current_user.hashed_password = get_password_hash(password_data.new_password)
    
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar la contraseña: {str(e)}"
        )

    return {"message": "Contraseña actualizada correctamente"}