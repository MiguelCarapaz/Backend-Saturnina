from fastapi import APIRouter, Depends, HTTPException, status, Path, Body
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete
from app.database import get_db
from app.models.category import Category
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter()

class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None

class CategoryOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

@router.get("/category", response_class=JSONResponse)
async def read_categories(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Category).order_by(Category.id).offset(skip).limit(limit))
        categories = result.scalars().all()
        detail = [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None
            } for c in categories
        ]
        return JSONResponse(content={"detail": detail}, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener categorías: {str(e)}")

@router.get("/category/{category_id}", response_class=JSONResponse)
async def read_category(category_id: int = Path(..., gt=0), db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Category).where(Category.id == category_id))
        category = result.scalar_one_or_none()
        if not category:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada")
        detail = {
            "id": category.id,
            "name": category.name,
            "description": category.description,
            "created_at": category.created_at.isoformat() if category.created_at else None,
            "updated_at": category.updated_at.isoformat() if category.updated_at else None
        }
        return JSONResponse(content={"detail": detail}, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener categoría: {str(e)}")

@router.post("/category", response_class=JSONResponse, status_code=201)
async def create_category(payload: CategoryCreate = Body(...), db: AsyncSession = Depends(get_db)):
    try:
        q = await db.execute(select(Category).where(Category.name == payload.name))
        if q.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Ya existe una categoría con ese nombre")

        new_cat = Category(name=payload.name, description=payload.description)
        db.add(new_cat)
        await db.commit()
        await db.refresh(new_cat)

        detail = {
            "id": new_cat.id,
            "name": new_cat.name,
            "description": new_cat.description,
            "created_at": new_cat.created_at.isoformat() if new_cat.created_at else None,
            "updated_at": new_cat.updated_at.isoformat() if new_cat.updated_at else None
        }
        return JSONResponse(content={"detail": detail}, status_code=201)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear categoría: {str(e)}")

@router.put("/category/{category_id}", response_class=JSONResponse)
async def update_category(category_id: int, payload: CategoryCreate = Body(...), db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Category).where(Category.id == category_id))
        category = result.scalar_one_or_none()
        if not category:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")

        await db.execute(
            update(Category)
            .where(Category.id == category_id)
            .values(name=payload.name, description=payload.description, updated_at=datetime.utcnow())
        )
        await db.commit()

        result = await db.execute(select(Category).where(Category.id == category_id))
        updated = result.scalar_one()
        detail = {
            "id": updated.id,
            "name": updated.name,
            "description": updated.description,
            "created_at": updated.created_at.isoformat() if updated.created_at else None,
            "updated_at": updated.updated_at.isoformat() if updated.updated_at else None
        }
        return JSONResponse(content={"detail": detail}, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al actualizar categoría: {str(e)}")

@router.delete("/category/{category_id}", status_code=204)
async def delete_category(category_id: int, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Category).where(Category.id == category_id))
        category = result.scalar_one_or_none()
        if not category:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")

        from app.models.product import Product
        prod_q = await db.execute(select(Product).where(Product.category_id == category_id))
        associated = prod_q.scalars().first()
        if associated:
            raise HTTPException(status_code=400, detail="No se puede eliminar: existen productos asociados a esta categoría")

        await db.execute(delete(Category).where(Category.id == category_id))
        await db.commit()
        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al eliminar categoría: {str(e)}")
