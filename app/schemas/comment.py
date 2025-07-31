from pydantic import BaseModel
from typing import Optional

class CommentBase(BaseModel):
    user_id: int
    product_id: int
    rating: int
    comment: str

class CommentCreate(CommentBase):
    pass

class CommentUpdate(BaseModel):
    rating: Optional[int] = None
    comment: Optional[str] = None

class CommentOut(CommentBase):
    id: int
    created_at: Optional[str]
    class Config:
        orm_mode = True
