from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import user as user_models
from app.schemas import user as user_schemas
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "testsecret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

router = APIRouter()

from sqlalchemy.future import select

async def get_user_by_email(db: AsyncSession, email: str):
    result = await db.execute(select(user_models.User).where(user_models.User.email == email))
    return result.scalars().first()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[int] = None):
    from datetime import datetime, timedelta
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_delta or ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    user = await get_user_by_email(db, form_data.username)
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Correo o contraseña incorrectos. Verifica tus datos.")
    token = create_access_token({"sub": user.email, "id": user.id, "role": user.role, "email": user.email})
    return {"detail": {"token": token, "id": user.id, "role": user.role, "email": user.email}}

@router.post("/register")
async def register(user: user_schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    db_user = await get_user_by_email(db, user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="El usuario ya existe")
    hashed_password = get_password_hash(user.password)
    new_user = user_models.User(
        name=user.name,
        last_name=user.last_name,
        email=user.email,
        password_hash=hashed_password,
        role="user",
        address=user.address,
        phone=user.phone
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return {"detail": {"id": new_user.id, "email": new_user.email, "name": new_user.name, "last_name": new_user.last_name, "role": new_user.role, "address": new_user.address, "phone": new_user.phone}}
