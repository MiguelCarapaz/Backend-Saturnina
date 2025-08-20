from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func
from typing import Optional, List, Dict, Any
from app.database import get_db
from app.models.comments import Comment
from app.models.user import User
from app.models.orders import Order, OrderItem

router = APIRouter()


async def _fetch_user_obj(db: AsyncSession, user_id: Optional[int]) -> Optional[Dict[str, Any]]:
    if user_id is None:
        return None
    q = await db.execute(select(User).where(User.id == int(user_id)))
    u = q.scalar_one_or_none()
    if not u:
        return None
    return {
        "id": getattr(u, "id", None),
        "nombre": getattr(u, "name", None) or getattr(u, "nombre", None) or "",
        "apellido": getattr(u, "last_name", None) or getattr(u, "apellido", None) or "",
        "email": getattr(u, "email", None),
        "telefono": getattr(u, "phone", None) or getattr(u, "telefono", None) or None,
    }


def _serialize_comment_row(row: Comment, user_obj: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    result = {
        "id": getattr(row, "id"),
        "_id": getattr(row, "id"),
        "descripcion": getattr(row, "comment", None) if getattr(row, "comment", None) is not None else getattr(row, "descripcion", None),
        "calificacion": getattr(row, "rating", None) if getattr(row, "rating", None) is not None else getattr(row, "calificacion", None),
        "comment": getattr(row, "comment", None),
        "rating": getattr(row, "rating", None),
        "id_producto": getattr(row, "product_id", None),
        "product_id": getattr(row, "product_id", None),
        "user_id": user_obj or {"id": getattr(row, "user_id", None)},
        "created_at": getattr(row, "created_at", None).isoformat() if getattr(row, "created_at", None) else None,
    }
    return result


@router.get("/comments")
async def get_comments(id_producto: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    try:
        query = select(Comment)

        if id_producto:
            parsed = None
            if isinstance(id_producto, str):
                if id_producto.isdigit():
                    parsed = int(id_producto)
                elif id_producto.startswith("product:"):
                    tail = id_producto.split("product:", 1)[1]
                    if tail.isdigit():
                        parsed = int(tail)
            if parsed is not None:
                query = query.where(Comment.product_id == parsed)
            else:
                query = query.where(Comment.product_id == None)  
        q = await db.execute(query)
        rows: List[Comment] = q.scalars().all()

        result = []
        for r in rows:
            user_obj = await _fetch_user_obj(db, getattr(r, "user_id", None))
            result.append(_serialize_comment_row(r, user_obj))

        return JSONResponse(content={"detail": [{"result": result}]}, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener comentarios: {str(e)}")


@router.get("/comments-general")
async def get_comments_general(db: AsyncSession = Depends(get_db)):
    try:
        q = await db.execute(select(Comment).where(Comment.product_id == None))
        rows: List[Comment] = q.scalars().all()
        result = []
        for r in rows:
            user_obj = await _fetch_user_obj(db, getattr(r, "user_id", None))
            result.append(_serialize_comment_row(r, user_obj))
        return JSONResponse(content={"detail": [{"result": result}]}, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener comentarios generales: {str(e)}")


async def _user_bought_product_and_finalized(db: AsyncSession, user_id: int, product_id: int) -> bool:
    q = await db.execute(
        select(OrderItem)
        .join(Order, OrderItem.order_id == Order.id)
        .where(
            Order.user_id == int(user_id),
            func.lower(Order.status) == "finalizado",
            OrderItem.product_id == int(product_id),
        )
    )
    rows = q.scalars().all()
    return len(rows) > 0


async def _user_has_any_finalized_order(db: AsyncSession, user_id: int) -> bool:
    q = await db.execute(
        select(Order).where(
            Order.user_id == int(user_id),
            func.lower(Order.status) == "finalizado"
        )
    )
    rows = q.scalars().all()
    return len(rows) > 0


@router.post("/comments", status_code=201)
async def create_comment(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Body JSON inválido")

    descripcion = payload.get("descripcion") or payload.get("comment") or payload.get("comentario")
    calificacion = payload.get("calificacion") or payload.get("rating")
    user_id = payload.get("user_id") or payload.get("user") or payload.get("usuario")
    id_producto = payload.get("id_producto") or payload.get("product_id") or payload.get("idProducto")

    if user_id is None or id_producto is None or calificacion is None or descripcion is None:
        raise HTTPException(status_code=400, detail="Datos incompletos para crear comentario")

    if isinstance(id_producto, str) and id_producto.startswith("product:"):
        tail = id_producto.split("product:", 1)[1]
        if tail.isdigit():
            id_producto = int(tail)

    try:
        bought = await _user_bought_product_and_finalized(db, int(user_id), int(id_producto))
        if not bought:
            raise HTTPException(status_code=406, detail="Necesitas esperar a que tu compra esté finalizada o comprar este producto para poder comentar")

        new = Comment(
            user_id=int(user_id),
            product_id=int(id_producto),
            rating=int(calificacion),
            comment=str(descripcion),
        )
        db.add(new)
        await db.commit()
        await db.refresh(new)

        user_obj = await _fetch_user_obj(db, new.user_id)
        out = _serialize_comment_row(new, user_obj)
        return JSONResponse(content={"result": out}, status_code=201)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear comentario: {str(e)}")


@router.put("/comments/{comment_id}")
async def update_comment(comment_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Body JSON inválido")

    q = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = q.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comentario no encontrado")

    descripcion = payload.get("descripcion") or payload.get("comment")
    calificacion = payload.get("calificacion") or payload.get("rating")

    dirty = False
    if descripcion is not None:
        comment.comment = str(descripcion)
        dirty = True
    if calificacion is not None:
        comment.rating = int(calificacion)
        dirty = True

    if dirty:
        await db.commit()
        await db.refresh(comment)
    else:
        await db.refresh(comment)

    user_obj = await _fetch_user_obj(db, getattr(comment, "user_id", None))
    out = _serialize_comment_row(comment, user_obj)
    return JSONResponse(content={"result": out}, status_code=200)


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(comment_id: int, db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = q.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comentario no encontrado")
    try:
        await db.delete(comment)
        await db.commit()
        return JSONResponse(status_code=204, content=None)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al eliminar comentario: {str(e)}")


@router.post("/comments-general", status_code=201)
async def create_comment_general(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Body JSON inválido")

    descripcion = payload.get("descripcion") or payload.get("comment")
    calificacion = payload.get("calificacion") or payload.get("rating")
    user_id = payload.get("user_id") or payload.get("user")

    if user_id is None or calificacion is None or descripcion is None:
        raise HTTPException(status_code=400, detail="Datos incompletos para crear comentario general")

    try:
        ok = await _user_has_any_finalized_order(db, int(user_id))
        if not ok:
            raise HTTPException(status_code=406, detail="Necesitas esperar a que tu compra esté finalizada o comprar algo para comentar")

        new = Comment(
            user_id=int(user_id),
            product_id=None,
            rating=int(calificacion),
            comment=str(descripcion),
        )
        db.add(new)
        await db.commit()
        await db.refresh(new)

        user_obj = await _fetch_user_obj(db, new.user_id)
        out = _serialize_comment_row(new, user_obj)
        return JSONResponse(content={"result": out}, status_code=201)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear comentario general: {str(e)}")


@router.put("/comments-general/{comment_id}")
async def update_comment_general(comment_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Body JSON inválido")

    q = await db.execute(select(Comment).where(Comment.id == comment_id, Comment.product_id == None))
    comment = q.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comentario general no encontrado")

    descripcion = payload.get("descripcion") or payload.get("comment")
    calificacion = payload.get("calificacion") or payload.get("rating")

    dirty = False
    if descripcion is not None:
        comment.comment = str(descripcion)
        dirty = True
    if calificacion is not None:
        comment.rating = int(calificacion)
        dirty = True

    if dirty:
        await db.commit()
        await db.refresh(comment)
    else:
        await db.refresh(comment)

    user_obj = await _fetch_user_obj(db, getattr(comment, "user_id", None))
    out = _serialize_comment_row(comment, user_obj)
    return JSONResponse(content={"result": out}, status_code=200)


@router.delete("/comments-general/{comment_id}", status_code=204)
async def delete_comment_general(comment_id: int, db: AsyncSession = Depends(get_db)):
    q = await db.execute(select(Comment).where(Comment.id == comment_id, Comment.product_id == None))
    comment = q.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comentario general no encontrado")
    try:
        await db.delete(comment)
        await db.commit()
        return JSONResponse(status_code=204, content=None)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al eliminar comentario general: {str(e)}")
