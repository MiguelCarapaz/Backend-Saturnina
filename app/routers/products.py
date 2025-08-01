from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database import get_db
from app.models.product import Product
from app.models.category import Category
from typing import List, Optional
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from datetime import datetime

router = APIRouter()

# ====================== MODELOS PYDANTIC ======================

class ImageSchema(BaseModel):
    secure_url: str
    public_id: Optional[str] = None

class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    images: Optional[List[ImageSchema]] = []
    category_id: int
    stock: int = 0
    is_active: bool = True

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    images: Optional[List[ImageSchema]] = None
    category_id: Optional[int] = None
    stock: Optional[int] = None
    is_active: Optional[bool] = None

class ProductOut(ProductBase):
    id: int
    id_producto: str  # Campo adicional para frontend
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class CategoryOut(CategoryBase):
    id: str  # Formateado como "category:id" para frontend
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ====================== FUNCIONES AUXILIARES ======================

async def get_product_or_404(db: AsyncSession, product_id: int):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado"
        )
    return product

async def get_category_or_404(db: AsyncSession, category_id: int):
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categoría no encontrada"
        )
    return category

def format_product_response(product: Product):
    return {
        "id": product.id,
        "id_producto": str(product.id),
        "name": product.name,
        "description": product.description,
        "price": float(product.price),
        "precio": float(product.price),  # Duplicado para compatibilidad frontend
        "images": [img for img in (product.images or [])],
        "imagen": [img for img in (product.images or [])],  # Duplicado para frontend
        "category_id": product.category_id,
        "category": product.category_id,  # Duplicado para frontend
        "stock": product.stock,
        "is_active": product.is_active,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "updated_at": product.updated_at.isoformat() if product.updated_at else None
    }

def format_category_response(category: Category):
    return {
        "id": f"category:{category.id}",
        "name": category.name,
        "description": category.description,
        "is_active": category.is_active,
        "created_at": category.created_at.isoformat() if category.created_at else None,
        "updated_at": category.updated_at.isoformat() if category.updated_at else None
    }


@router.get("/products", response_class=JSONResponse)
async def read_products(
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    try:
        query = select(Product)
        
        if is_active is not None:
            query = query.where(Product.is_active == is_active)
            
        result = await db.execute(
            query.order_by(Product.id)
            .offset(skip)
            .limit(limit)
        )
        products = result.scalars().all()
        
        return JSONResponse(
            content={
                "detail": [format_product_response(product) for product in products]
            },
            status_code=200
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener productos: {str(e)}"
        )

@router.get("/products/{product_id}", response_class=JSONResponse)
async def read_product(
    product_id: int, 
    db: AsyncSession = Depends(get_db)
):
    try:
        product = await get_product_or_404(db, product_id)
        return JSONResponse(
            content={"detail": format_product_response(product)},
            status_code=200
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener producto: {str(e)}"
        )

@router.post("/products", response_class=JSONResponse, status_code=201)
async def create_product(
    product: ProductCreate,
    db: AsyncSession = Depends(get_db)
):
    try:
        # Verificar categoría existente
        await get_category_or_404(db, product.category_id)
        
        # Verificar nombre único
        existing_product = await db.execute(
            select(Product).where(Product.name == product.name)
        )
        if existing_product.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe un producto con este nombre"
            )
        
        new_product = Product(**product.dict())
        db.add(new_product)
        await db.commit()
        await db.refresh(new_product)
        
        return JSONResponse(
            content={"detail": format_product_response(new_product)},
            status_code=201
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear producto: {str(e)}"
        )

@router.put("/products/{product_id}", response_class=JSONResponse)
async def update_product(
    product_id: int,
    product_update: ProductUpdate,
    db: AsyncSession = Depends(get_db)
):
    try:
        product = await get_product_or_404(db, product_id)
        
        update_data = product_update.dict(exclude_unset=True)
        
        if "category_id" in update_data:
            await get_category_or_404(db, update_data["category_id"])
        
        for field, value in update_data.items():
            setattr(product, field, value)
            
        product.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(product)
        
        return JSONResponse(
            content={"detail": format_product_response(product)},
            status_code=200
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar producto: {str(e)}"
        )

@router.delete("/products/{product_id}", status_code=204)
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        product = await get_product_or_404(db, product_id)
        await db.delete(product)
        await db.commit()
        return JSONResponse(content=None, status_code=204)
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar producto: {str(e)}"
        )

# ====================== ENDPOINTS DE CATEGORÍAS ======================

@router.get("/category", response_class=JSONResponse)
async def read_categories(
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    try:
        query = select(Category)
        
        if is_active is not None:
            query = query.where(Category.is_active == is_active)
            
        result = await db.execute(
            query.order_by(Category.id)
            .offset(skip)
            .limit(limit)
        )
        categories = result.scalars().all()
        
        response_data = [format_category_response(cat) for cat in categories]
        
        # Agregar opción "Todos"
        response_data.insert(0, {
            "id": "category:todos",
            "name": "Todos",
            "description": "Todos los productos",
            "is_active": True,
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

@router.get("/category/{category_id}", response_class=JSONResponse)
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
                        "is_active": True,
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

@router.post("/category", response_class=JSONResponse, status_code=201)
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

@router.put("/category/{category_id}", response_class=JSONResponse)
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

@router.delete("/category/{category_id}", status_code=204)
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        category = await get_category_or_404(db, category_id)
        
        product_exists = await db.execute(
            select(Product)
            .where(Product.category_id == category_id)
            .limit(1)  # Solo necesitamos saber si existe al menos uno
        )
        
        if product_exists.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,  # 409 Conflict es más semántico
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
