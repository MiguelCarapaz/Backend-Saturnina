from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
import os
import secrets
from dotenv import load_dotenv
from pydantic import BaseModel, EmailStr, validator
from sqlalchemy.future import select
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
from fastapi.responses import JSONResponse

# Cargar variables de entorno
load_dotenv()

# Configuración JWT
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError(
        "SECRET_KEY no configurada en variables de entorno. "
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")

# Definición de roles
ADMIN_ROLE = "rol:74rvq7jatzo6ac19mc79"
USER_ROLE = "rol:vuqn7k4vw0m1a3wt7fkb"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

router = APIRouter(tags=["authentication"])

# Esquemas
class LoginForm(BaseModel):
    email: str
    password: str

class RegisterForm(BaseModel):
    nombre: str
    apellido: str
    email: str
    password: str
    telefono: str

    @validator('nombre', 'apellido')
    def validate_name_length(cls, v):
        if len(v) < 3 or len(v) > 10:
            raise ValueError('Debe tener entre 3 y 10 caracteres')
        return v

    @validator('password')
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

    @validator('telefono')
    def validate_phone(cls, v):
        if len(v) != 10 or not v.isdigit():
            raise ValueError('El teléfono debe tener exactamente 10 dígitos')
        return v

class TokenResponse(BaseModel):
    token: str
    token_type: str
    user: dict

class TokenData(BaseModel):
    email: Optional[str] = None

# Funciones auxiliares
async def get_user_by_email(db: AsyncSession, email: str):
    result = await db.execute(select(User).where(User.email == email))
    return result.scalars().first()

def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def send_verification_email(email: str, token: str, background_tasks: BackgroundTasks):
    verification_url = f"https://saturnina.vercel.app/confirmar/{token}"
    
    # Validar configuración de email
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        raise RuntimeError("Configuración de email incompleta")
    
    message = MIMEMultipart()
    message["From"] = EMAIL_SENDER
    message["To"] = email
    message["Subject"] = "Verifica tu cuenta en Saturnina"
    
    body = f"""
    ¡Bienvenido a Saturnina!
    
    Por favor verifica tu cuenta haciendo clic en el siguiente enlace:
    {verification_url}
    
    Este enlace expirará en 24 horas.
    """
    
    message.attach(MIMEText(body, "plain"))
    
    def send_email():
        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                server.send_message(message)
        except Exception as e:
            print(f"Error enviando email: {e}")
    
    background_tasks.add_task(send_email)

# Endpoints 
@router.post("/login")
async def login(form_data: LoginForm, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_email(db, form_data.email)
    
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta inactiva. Por favor verifica tu email primero."
        )
    
    role_mapping = {
        "admin": ADMIN_ROLE,
        "user": USER_ROLE
    }
    
    frontend_role = role_mapping.get(user.role, USER_ROLE)
    
    access_token = create_access_token(data={"sub": user.email})
    
    return {
        "detail": {
            "token": access_token,
            "id": str(user.id),
            "rol": frontend_role,
            "email": user.email,
            "nombre": user.name,
            "apellido": user.last_name,
            "telefono": user.phone
        }
    }

@router.post("/register", response_model=dict)
async def register(
    user_data: RegisterForm, 
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    try:
        existing_user = await get_user_by_email(db, user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este correo electrónico ya se encuentra en uso"
            )

        hashed_password = get_password_hash(user_data.password)
        new_user = User(
            name=user_data.nombre,
            last_name=user_data.apellido,
            email=user_data.email,
            password_hash=hashed_password,
            role="user",
            phone=user_data.telefono,
            is_active=False
        )
        
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        
        verification_token = create_access_token(
            data={"sub": new_user.email, "purpose": "email_verification"},
            expires_delta=timedelta(hours=24)
        )
        
        await send_verification_email(
            email=new_user.email,
            token=verification_token,
            background_tasks=background_tasks
        )
        
        return {
            "message": "Registro exitoso. Por favor verifica tu email para activar tu cuenta.",
            "user_id": str(new_user.id)
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/check-email/{token}")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Token de verificación inválido o expirado"
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        purpose: str = payload.get("purpose")

        if email is None or purpose != "email_verification":
            raise credentials_exception

        user = await get_user_by_email(db, email)
        if not user:
            raise credentials_exception

        if user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Este correo ya está confirmado"
            )

        user.is_active = True
        db.add(user)  
        await db.commit()
        await db.refresh(user)

        return {"message": "Email verificado correctamente. Ya puedes iniciar sesión."}

    except JWTError:
        raise credentials_exception

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception
    
    user = await get_user_by_email(db, email=token_data.email)
    if user is None:
        raise credentials_exception
    return user


# ----------------------------
# 🔹 Nueva implementación: Recuperación de contraseña
# ----------------------------

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

async def send_recover_email(email: str, token: str, background_tasks: BackgroundTasks):
    url = f"https://saturnina.vercel.app/recuperar/{token}"

    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        raise RuntimeError("Config de email incompleta")

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
            print(f"Error enviando email de recuperación: {e}")

    background_tasks.add_task(send_email)

@router.post("/recover-password")
async def recover_password(
    data: RecoverPasswordRequest,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    user = await get_user_by_email(db, data.email)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if not user.is_active:
        raise HTTPException(status_code=422, detail="Necesita activar su cuenta")

    token = create_access_token(
        data={"sub": user.email, "purpose": "password_recovery"},
        expires_delta=timedelta(hours=1)
    )

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
async def new_password(
    token: str,
    data: PasswordUpdate,
    db: AsyncSession = Depends(get_db)
):
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
