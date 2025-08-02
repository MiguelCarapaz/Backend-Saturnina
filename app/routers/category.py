from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from datetime import datetime
from app.database import get_db
from app.models.category import Category

router = APIRouter(prefix="/category", tags=["categories"])

# ====================== MODELOS PYDANTIC ======================

class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class CategoryOut(CategoryBase):
    id: str  # Formateado como "category:id" para frontend
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ====================== FUNCIONES AUXILIARES ======================

async def get_category_or_404(db: AsyncSession, category_id: int):
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categoría no encontrada"
        )
    return category

def format_category_response(category: Category):
    return {
        "id": f"category:{category.id}",
        "name": category.name,
        "description": category.description,
        "created_at": category.created_at.isoformat() if category.created_at else None,
        "updated_at": category.updated_at.isoformat() if category.updated_at else None
    }

# ====================== ENDPOINTS DE CATEGORÍAS ======================

@router.get("", response_class=JSONResponse)
async def read_categories(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    try:
        query = select(Category)
            
        result = await db.execute(
            query.order_by(Category.id)
            .offset(skip)
            .limit(limit)
        )
        categories = result.scalars().all()
        
        response_data = [format_category_response(cat) for cat in categories]
        
        # Agregar opción "Todos" que espera el frontend
        response_data.insert(0, {
            "id": "category:todos",
            "name": "Todos",
            "description": "Todos los productos",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": None
        })
        
        return JSONResponse(
            content={"detail": response_data},
            status_code=200
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener categorías: {str(e)}"
        )

@router.get("/{category_id}", response_class=JSONResponse)
async def read_category(
    category_id: str,  # Acepta "todos" o ID numérico
    db: AsyncSession = Depends(get_db)
):
    try:
        if category_id == "todos":
            return JSONResponse(
                content={
                    "detail": {
                        "id": "category:todos",
                        "name": "Todos",
                        "description": "Todos los productos",
                        "created_at": datetime.utcnow().isoformat(),
                        "updated_at": None
                    }
                },
                status_code=200
            )
            
        category = await get_category_or_404(db, int(category_id))
        return JSONResponse(
            content={"detail": format_category_response(category)},
            status_code=200
        )
        
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID de categoría inválido"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener categoría: {str(e)}"
        )

@router.post("", response_class=JSONResponse, status_code=201)
async def create_category(
    category: CategoryCreate,
    db: AsyncSession = Depends(get_db)
):
    try:
        # Verificar nombre único
        existing_cat = await db.execute(
            select(Category).where(Category.name == category.name))
        if existing_cat.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe una categoría con este nombre"
            )
            
        new_category = Category(**category.dict())
        db.add(new_category)
        await db.commit()
        await db.refresh(new_category)
        
        return JSONResponse(
            content={"detail": format_category_response(new_category)},
            status_code=201
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear categoría: {str(e)}"
        )

@router.put("/{category_id}", response_class=JSONResponse)
async def update_category(
    category_id: int,
    category_update: CategoryUpdate,
    db: AsyncSession = Depends(get_db)
):
    try:
        category = await get_category_or_404(db, category_id)
        
        update_data = category_update.dict(exclude_unset=True)
        
        if "name" in update_data:
            # Verificar nombre único
            existing_cat = await db.execute(
                select(Category)
                .where(Category.name == update_data["name"])
                .where(Category.id != category_id)
            )
            if existing_cat.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ya existe una categoría con este nombre"
                )
        
        for field, value in update_data.items():
            setattr(category, field, value)
            
        category.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(category)
        
        return JSONResponse(
            content={"detail": format_category_response(category)},
            status_code=200
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar categoría: {str(e)}"
        )

@router.delete("/{category_id}", status_code=204)
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        category = await get_category_or_404(db, category_id)
        
        # Verificar si hay productos asociados
        product_exists = await db.execute(
            select(Product)
            .where(Product.category_id == category_id)
            .limit(1)
        )
        
        if product_exists.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No se puede eliminar: existen productos asociados a esta categoría"
            )
        
        await db.delete(category)
        await db.commit()
        
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    
    except HTTPException as http_exc:
        raise http_exc
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al eliminar categoría: {str(exc)}"
        ) from exc