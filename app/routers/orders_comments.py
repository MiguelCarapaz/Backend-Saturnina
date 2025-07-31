from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database import get_db
from app.models.comment import Comment
from app.models.order import Order, OrderItem
from app.schemas.comment import CommentCreate, CommentUpdate, CommentOut
from app.schemas.order import OrderCreate, OrderOut, OrderItemCreate, OrderItemOut
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

# --- Pedidos ---
@router.get("/orders", response_model=List[OrderOut])
async def get_orders(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Order))
    orders = result.scalars().all()
    return orders

@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(order_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return order

@router.post("/orders", response_model=OrderOut, status_code=201)
async def create_order(order: OrderCreate, db: AsyncSession = Depends(get_db)):
    new_order = Order(user_id=order.user_id, total=order.total, status=order.status)
    db.add(new_order)
    await db.commit()
    await db.refresh(new_order)
    # Crear items
    for item in order.items:
        new_item = OrderItem(order_id=new_order.id, **item.dict())
        db.add(new_item)
    await db.commit()
    await db.refresh(new_order)
    return new_order

@router.put("/orders/{order_id}", response_model=OrderOut)
async def update_order(order_id: int, order: OrderCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Order).where(Order.id == order_id))
    db_order = result.scalar_one_or_none()
    if not db_order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    db_order.user_id = order.user_id
    db_order.total = order.total
    db_order.status = order.status
    await db.commit()
    await db.refresh(db_order)
    return db_order

@router.delete("/orders/{order_id}", status_code=204)
async def delete_order(order_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Order).where(Order.id == order_id))
    db_order = result.scalar_one_or_none()
    if not db_order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    await db.delete(db_order)
    await db.commit()
    return
