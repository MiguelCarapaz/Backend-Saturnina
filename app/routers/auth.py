from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel, EmailStr, validator
from typing import Optional, Dict, Any
from jose import jwt, JWTError
from datetime import timedelta, datetime
from passlib.context import CryptContext
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.database import get_db
from app.models.user import User

# --- Configuración ---
router = APIRouter(tags=["authentication"])

SECRET_KEY = "supersecret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

EMAIL_SENDER = "tu_correo@gmail.com"
EMAIL_PASSWORD = "tu_password"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Utilidades ---
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_user_by_email(db: AsyncSession, email: str):
    result = await db.execute(select(User).where(User.email == email))
    return result.scalars().first()

# --- Schemas ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class RecoverPasswordRequest(BaseModel):
    email: str

class PasswordUpdate(BaseModel):
    new_password: str
    confirm_password: str

    @validator('new_password')
    def validate_password(cls, v):
        if len(v) < 9 or len(v) > 18:
            raise ValueError('La contraseña debe tener entre 9 y 18 caracteres')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Debe contener al menos una mayúscula')
        if not re.search(r'\d', v):
            raise ValueError('Debe contener al menos un número')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Debe contener al menos un carácter especial')
        return v

# --- Email helpers ---
async def send_verification_email(email: str, token: str, background_tasks: BackgroundTasks):
    url = f"https://saturnina.vercel.app/verify/{token}"
    message = MIMEMultipart()
    message["From"] = EMAIL_SENDER
    message["To"] = email
    message["Subject"] = "Verifica tu cuenta en Saturnina"
    body = f"Activa tu cuenta haciendo clic en: {url}"
    message.attach(MIMEText(body, "plain"))

    def send_email():
        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                server.send_message(message)
        except Exception as e:
            print(f"Error enviando correo de verificación: {e}")

    background_tasks.add_task(send_email)

async def send_recover_email(email: str, token: str, background_tasks: BackgroundTasks):
    url = f"https://saturnina.vercel.app/recuperar/{token}"
    message = MIMEMultipart()
    message["From"] = EMAIL_SENDER
    message["To"] = email
    message["Subject"] = "Recupera tu contraseña en Saturnina"
    body = f"""
    Has solicitado recuperar tu cuenta.

    Haz clic en el siguiente enlace para restablecer tu contraseña:
    {url}

    Este enlace expira en 1 hora.
    """
    message.attach(MIMEText(body, "plain"))

    def send_email():
        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                server.send_message(message)
        except Exception as e:
            print(f"Error enviando correo de recuperación: {e}")

    background_tasks.add_task(send_email)

# --- Endpoints ---
@router.post("/register")
async def register_user(user: UserCreate, db: AsyncSession = Depends(get_db), background_tasks: BackgroundTasks = BackgroundTasks()):
    db_user = await get_user_by_email(db, user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="El email ya está registrado")

    hashed_password = get_password_hash(user.password)
    new_user = User(email=user.email, password_hash=hashed_password, is_active=False)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    token = create_access_token({"sub": new_user.email, "purpose": "account_verification"}, expires_delta=timedelta(hours=24))
    await send_verification_email(new_user.email, token, background_tasks)

    return {"msg": "Usuario registrado. Verifica tu correo electrónico."}

@router.post("/login", response_model=Token)
async def login(user: UserLogin, db: AsyncSession = Depends(get_db)):
    db_user = await get_user_by_email(db, user.email)
    if not db_user or not verify_password(user.password, db_user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

    if not db_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cuenta no verificada")

    access_token = create_access_token(data={"sub": db_user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/verify/{token}")
async def verify_account(token: str, db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        purpose = payload.get("purpose")
        if not email or purpose != "account_verification":
            raise HTTPException(status_code=400, detail="Token inválido")
        user = await get_user_by_email(db, email)
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        user.is_active = True
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return {"msg": "Cuenta verificada exitosamente"}
    except JWTError:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")

# --- Recuperación de contraseña ---
@router.post("/recover-password")
async def recover_password(data: RecoverPasswordRequest, db: AsyncSession = Depends(get_db), background_tasks: BackgroundTasks = BackgroundTasks()):
    user = await get_user_by_email(db, data.email)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not user.is_active:
        raise HTTPException(status_code=422, detail="Necesita activar su cuenta")

    token = create_access_token(data={"sub": user.email, "purpose": "password_recovery"}, expires_delta=timedelta(hours=1))
    await send_recover_email(user.email, token, background_tasks)
    return {"message": "Se ha enviado un correo de recuperación"}

@router.get("/recover-password/{token}")
async def verify_recover_token(token: str, db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        purpose = payload.get("purpose")
        if not email or purpose != "password_recovery":
            raise HTTPException(status_code=400, detail="Token inválido")
        user = await get_user_by_email(db, email)
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return {"msg": "Token válido. Puede restablecer su contraseña."}
    except JWTError:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")

@router.post("/new-password/{token}")
async def new_password(token: str, data: PasswordUpdate, db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        purpose = payload.get("purpose")
        if not email or purpose != "password_recovery":
            raise HTTPException(status_code=400, detail="Token inválido")

        user = await get_user_by_email(db, email)
        if not user:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        if data.new_password != data.confirm_password:
            raise HTTPException(status_code=400, detail="Las contraseñas no coinciden")

        if verify_password(data.new_password, user.password_hash):
            raise HTTPException(status_code=406, detail="La nueva contraseña no puede ser igual a la actual")

        user.password_hash = get_password_hash(data.new_password)
        db.add(user)
        await db.commit()
        await db.refresh(user)

        return JSONResponse(status_code=200, content={"msg": "Contraseña actualizada correctamente"})
    except JWTError:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")
