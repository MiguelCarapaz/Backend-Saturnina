from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from app.database import get_db
from app.models.product import Product, ProductImage
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

class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    category_id: int
    stock: int = 0

class ProductCreate(ProductBase):
    images: List[ImageSchema] = []

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category_id: Optional[int] = None
    stock: Optional[int] = None
    images: Optional[List[ImageSchema]] = None

class ProductOut(BaseModel):
    id: int
    id_producto: str
    name: str
    descripcion: Optional[str] = None
    precio: float
    imagen: List[dict]
    category: int
    stock: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class CategoryOut(CategoryBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# ====================== FUNCIONES AUXILIARES ======================

async def get_product_or_404(db: AsyncSession, product_id: int):
    result = await db.execute(
        select(Product)
        .options(
            joinedload(Product.images),
            joinedload(Product.category)  # ¡Carga la categoría!
        )
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Producto no encontrado"
        )
    return product

@router.get("/products", response_class=JSONResponse)
async def read_products(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    try:
        query = select(Product).options(
            joinedload(Product.images),
            joinedload(Product.category)  # ¡Carga la categoría!
        )
            
        result = await db.execute(
            query.order_by(Product.id)
            .offset(skip)
            .limit(limit)
        )
        products = result.scalars().unique().all()
        
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
    # Cargar la categoría si no está cargada
    category_name = ""
    if hasattr(product, 'category') and product.category:
        category_name = product.category.name
    elif product.category_id:
        # Opcional: Puedes cargar la categoría aquí si es necesario
        pass

    imagenes_formateadas = []
    if product.images:
        for img in product.images:
            imagenes_formateadas.append({
                "secure_url": img.image_url,
                "public_id": f"temp_{img.id}",
                "main": img.is_main
            })
    
    return {
        "id": product.id,
        "id_producto": str(product.id),
        "name": product.name,
        "descripcion": product.description,
        "precio": float(product.price),
        "imagen": imagenes_formateadas,
        "category": product.category_id,
        "category_id": product.category_id,
        "category_name": category_name,  # Usamos el nombre obtenido
        "stock": product.stock,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "updated_at": product.updated_at.isoformat() if product.updated_at else None
    }

def format_category_response(category: Category):
    return {
        "id": f"category:{category.id}",
        "name": category.name,
        "description": category.description,
        "created_at": category.created_at.isoformat() if category.created_at else None,
        "updated_at": category.updated_at.isoformat() if category.updated_at else None
    }

# ====================== ENDPOINTS DE PRODUCTOS ======================

@router.get("/products", response_class=JSONResponse)
async def read_products(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    try:
        query = select(Product).options(joinedload(Product.images))
            
        result = await db.execute(
            query.order_by(Product.id)
            .offset(skip)
            .limit(limit)
        )
        products = result.scalars().unique().all()
        
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

@router.get("/products/featured", response_class=JSONResponse)
async def get_featured_products(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            select(Product)
            .options(joinedload(Product.images))
            .order_by(Product.created_at.desc())
            .limit(8)
        )
        products = result.scalars().unique().all()
        
        return JSONResponse(
            content={"detail": [format_product_response(p) for p in products]},
            status_code=200
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        await get_category_or_404(db, product.category_id)
        
        existing_product = await db.execute(
            select(Product).where(Product.name == product.name)
        )
        if existing_product.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ya existe un producto con este nombre"
            )
        
        product_data = product.dict(exclude={"images"})
        new_product = Product(**product_data)
        db.add(new_product)
        await db.commit()
        await db.refresh(new_product)
        
        if product.images:
            for img in product.images:
                new_image = ProductImage(
                    product_id=new_product.id,
                    image_url=img.image_url,
                    is_main=img.is_main
                )
                db.add(new_image)
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
        
        update_data = product_update.dict(exclude_unset=True, exclude={"images"})
        
        if "category_id" in update_data:
            await get_category_or_404(db, update_data["category_id"])
        
        for field, value in update_data.items():
            setattr(product, field, value)
        
        if product_update.images is not None:
            await db.execute(
                delete(ProductImage)
                .where(ProductImage.product_id == product_id)
            )
            
            for img in product_update.images:
                new_image = ProductImage(
                    product_id=product_id,
                    image_url=img.image_url,
                    is_main=img.is_main
                )
                db.add(new_image)
        
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
        return Response(status_code=status.HTTP_204_NO_CONTENT)
        
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

@router.get("/category/{category_id}", response_class=JSONResponse)
async def read_category(
    category_id: str,
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

@router.post("/category", response_class=JSONResponse, status_code=201)
async def create_category(
    category: CategoryCreate,
    db: AsyncSession = Depends(get_db)
):
    try:
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