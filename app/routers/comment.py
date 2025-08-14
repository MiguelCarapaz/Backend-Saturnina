from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database import get_db
from app.models.comment import Comment
from app.schemas.comment import CommentCreate, CommentUpdate, CommentOut
from typing import List

router = APIRouter()

# --- Comentarios ---
@router.get("/comments", response_model=List[CommentOut])
async def get_comments(product_id: int = None, db: AsyncSession = Depends(get_db)):
    query = select(Comment)
    if product_id:
        query = query.where(Comment.product_id == product_id)
    result = await db.execute(query)
    comments = result.scalars().all()
    return comments

@router.post("/comments", response_model=CommentOut, status_code=201)
async def create_comment(comment: CommentCreate, db: AsyncSession = Depends(get_db)):
    new_comment = Comment(**comment.dict())
    db.add(new_comment)
    await db.commit()
    await db.refresh(new_comment)
    return new_comment

@router.put("/comments/{comment_id}", response_model=CommentOut)
async def update_comment(comment_id: int, comment: CommentUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    db_comment = result.scalar_one_or_none()
    if not db_comment:
        raise HTTPException(status_code=404, detail="Comentario no encontrado")
    for key, value in comment.dict(exclude_unset=True).items():
        setattr(db_comment, key, value)
    await db.commit()
    await db.refresh(db_comment)
    return db_comment

@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(comment_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    db_comment = result.scalar_one_or_none()
    if not db_comment:
        raise HTTPException(status_code=404, detail="Comentario no encontrado")
    await db.delete(db_comment)
    await db.commit()
    return
