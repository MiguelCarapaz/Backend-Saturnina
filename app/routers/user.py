from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, constr

from app.database import get_db
from app.models.user import User
from .auth import get_current_user, get_password_hash, verify_password

# Router for user profile actions (GET, PUT)
router = APIRouter(
    prefix="/user",
    tags=["users"],
    dependencies=[Depends(get_current_user)]
)

# Router for password update, as it has a different path structure
password_router = APIRouter(
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

async def get_user_profile(user_id: int, current_user: User = Depends(get_current_user)):
    """
    Fetches a user's profile information.
    A user can only fetch their own profile.
    """
    # Ensure the logged-in user is requesting their own profile
    if current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this profile")

    user = current_user

    # The frontend expects the data inside a "detail" object
    return {"detail": {
        "nombre": user.name,
        "apellido": user.last_name,
        "telefono": user.phone,
        "email": user.email
    }}

async def update_user_profile(user_id: int, user_data: UserUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Updates a user's profile information.
    A user can only update their own profile.
    """
    # Ensure the logged-in user is updating their own profile
    if current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this profile")

    user = current_user

    # Update user fields from the request data
    user.name = user_data.nombre
    user.last_name = user_data.apellido
    user.phone = user_data.telefono

    try:
        await db.commit()
        await db.refresh(user)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error updating profile: {e}")

    return {"message": "Profile updated successfully"}


async def update_password(password_data: PasswordUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Updates the current user's password.
    """
    # Check if the two password fields match
    if password_data.new_password != password_data.check_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, 
            detail="Las contraseñas no coinciden."
        )

    # Check if the new password is the same as the old one
    if verify_password(password_data.new_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE, 
            detail="La contraseña es igual a la anterior."
        )

    # Hash the new password and update it in the database
    current_user.hashed_password = get_password_hash(password_data.new_password)
    await db.commit()

    return {"message": "Contraseña actualizada con éxito."}