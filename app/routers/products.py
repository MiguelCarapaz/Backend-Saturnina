from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from app.database import get_db
from app.models.product import Product, ProductImage, ProductSize, ProductColor
from app.models.category import Category
from typing import List, Optional
from pydantic import BaseModel
from fastapi.responses import JSONResponse, Response
from datetime import datetime
from sqlalchemy.orm import joinedload

router = APIRouter()

# ====================== MODELOS PYDANTIC ======================

class ImageSchema(BaseModel):
    id: Optional[int] = None
    image_url: str
    is_main: bool = False

class SizeSchema(BaseModel):
    name: str

class ColorSchema(BaseModel):
    name: str

class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    category_id: int
    stock: int = 0

class ProductCreate(ProductBase):
    images: List[ImageSchema] = []
    tallas: List[SizeSchema] = []
    colores: List[ColorSchema] = []

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category_id: Optional[int] = None
    stock: Optional[int] = None
    images: Optional[List[ImageSchema]] = None
    tallas: Optional[List[SizeSchema]] = None
    colores: Optional[List[ColorSchema]] = None

class ProductOut(BaseModel):
    id: int
    id_producto: str
    name: str
    descripcion: Optional[str] = None
    precio: float
    imagen: List[dict]
    tallas: List[dict]
    colores: List[dict]
    category: int
    stock: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ====================== FUNCIONES AUXILIARES ======================

async def get_product_or_404(db: AsyncSession, product_id: int):
    result = await db.execute(
        select(Product)
        .options(
            joinedload(Product.images),
            joinedload(Product.category),
            joinedload(Product.sizes),
            joinedload(Product.colors)
        )
        .where(Product.id == product_id)
    )
    product = result.unique().scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado"
        )
    return product

def format_product_response(product: Product):
    imagenes_formateadas = [
        {
            "secure_url": img.image_url,
            "public_id": f"temp_{img.id}",
            "main": img.is_main
        } for img in product.images
    ] if product.images else []

    tallas_formateadas = [{"name": s.name} for s in product.sizes] if product.sizes else []
    colores_formateadas = [{"name": c.name} for c in product.colors] if product.colors else []

    return {
        "id": product.id,
        "id_producto": str(product.id),
        "name": product.name,
        "descripcion": product.description,
        "precio": float(product.price),
        "imagen": imagenes_formateadas,
        "tallas": tallas_formateadas,
        "colores": colores_formateadas,
        "category": product.category.id if product.category else product.category_id,
        "stock": product.stock,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "updated_at": product.updated_at.isoformat() if product.updated_at else None
    }

# ====================== ENDPOINTS DE PRODUCTOS ======================

@router.get("/products", response_class=JSONResponse)
async def read_products(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            select(Product)
            .options(
                joinedload(Product.images),
                joinedload(Product.category),
                joinedload(Product.sizes),
                joinedload(Product.colors)
            )
            .order_by(Product.id)
            .offset(skip)
            .limit(limit)
        )
        products = result.unique().scalars().all()
        return JSONResponse(content={"detail": [format_product_response(product) for product in products]}, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener productos: {str(e)}")

@router.get("/products/featured", response_class=JSONResponse)
async def get_featured_products(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            select(Product)
            .options(
                joinedload(Product.images),
                joinedload(Product.category),
                joinedload(Product.sizes),
                joinedload(Product.colors)
            )
            .order_by(Product.created_at.desc())
            .limit(8)
        )
        products = result.unique().scalars().all()
        return JSONResponse(content={"detail": [format_product_response(p) for p in products]}, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/products/{product_id}", response_class=JSONResponse)
async def read_product(product_id: int, db: AsyncSession = Depends(get_db)):
    try:
        product = await get_product_or_404(db, product_id)
        return JSONResponse(content={"detail": format_product_response(product)}, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener producto: {str(e)}")

@router.post("/products", response_class=JSONResponse, status_code=201)
async def create_product(product: ProductCreate, db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(select(Category).where(Category.id == product.category_id)).scalar_one()

        existing_product = await db.execute(select(Product).where(Product.name == product.name))
        if existing_product.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Ya existe un producto con este nombre")
        
        product_data = product.dict(exclude={"images", "tallas", "colores"})
        new_product = Product(**product_data)
        db.add(new_product)
        await db.commit()
        await db.refresh(new_product)

        # Guardar imágenes
        if product.images:
            for img in product.images:
                db.add(ProductImage(product_id=new_product.id, image_url=img.image_url, is_main=img.is_main))

        # Guardar tallas
        if product.tallas:
            for talla in product.tallas:
                db.add(ProductSize(product_id=new_product.id, name=talla.name))

        # Guardar colores
        if product.colores:
            for color in product.colores:
                db.add(ProductColor(product_id=new_product.id, name=color.name))

        await db.commit()
        await db.refresh(new_product)

        return JSONResponse(content={"detail": format_product_response(new_product)}, status_code=201)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear producto: {str(e)}")

@router.put("/products/{product_id}", response_class=JSONResponse)
async def update_product(product_id: int, product_update: ProductUpdate, db: AsyncSession = Depends(get_db)):
    try:
        product = await get_product_or_404(db, product_id)
        update_data = product_update.dict(exclude_unset=True, exclude={"images", "tallas", "colores"})

        if "category_id" in update_data:
            await db.execute(select(Category).where(Category.id == update_data["category_id"])).scalar_one()

        for field, value in update_data.items():
            setattr(product, field, value)

        # Actualizar imágenes
        if product_update.images is not None:
            await db.execute(delete(ProductImage).where(ProductImage.product_id == product_id))
            for img in product_update.images:
                db.add(ProductImage(product_id=product_id, image_url=img.image_url, is_main=img.is_main))

        # Actualizar tallas
        if product_update.tallas is not None:
            await db.execute(delete(ProductSize).where(ProductSize.product_id == product_id))
            for talla in product_update.tallas:
                db.add(ProductSize(product_id=product_id, name=talla.name))

        # Actualizar colores
        if product_update.colores is not None:
            await db.execute(delete(ProductColor).where(ProductColor.product_id == product_id))
            for color in product_update.colores:
                db.add(ProductColor(product_id=product_id, name=color.name))

        product.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(product)

        return JSONResponse(content={"detail": format_product_response(product)}, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al actualizar producto: {str(e)}")

@router.delete("/products/{product_id}", status_code=204)
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db)):
    try:
        product = await get_product_or_404(db, product_id)
        await db.delete(product)
        await db.commit()
        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al eliminar producto: {str(e)}")
