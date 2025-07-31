from pydantic import BaseModel
from typing import Optional

class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    stock: Optional[int] = 0
    image_url: Optional[str] = None
    category_id: Optional[int] = None

class ProductCreate(ProductBase):
    pass

class ProductUpdate(ProductBase):
    pass

class ProductOut(ProductBase):
    id: int
    class Config:
        orm_mode = True
