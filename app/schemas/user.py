from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    name: str
    last_name: str
    email: EmailStr
    password: str
    address: str = None
    phone: str = None

class UserOut(BaseModel):
    id: int
    name: str
    last_name: str
    email: EmailStr
    role: str
    address: str = None
    phone: str = None

    class Config:
        orm_mode = True