from pydantic import BaseModel
from typing import Optional, List

class OrderItemBase(BaseModel):
    product_id: int
    quantity: int
    price: float

class OrderItemCreate(OrderItemBase):
    pass

class OrderItemOut(OrderItemBase):
    id: int
    class Config:
        orm_mode = True

class OrderBase(BaseModel):
    user_id: int
    total: float
    status: Optional[str] = "pendiente"

class OrderCreate(OrderBase):
    items: List[OrderItemCreate]

class OrderOut(OrderBase):
    id: int
    items: List[OrderItemOut]
    created_at: Optional[str]
    class Config:
        orm_mode = True
