from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database import get_db
from app.models.product import Product
from app.models.category import Category
from app.schemas.product import ProductCreate, ProductUpdate, ProductOut
from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryOut
from typing import List

router = APIRouter()

# PRODUCTOS
@router.get("/products", response_model=List[ProductOut])
async def get_products(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product))
    products = result.scalars().all()
    return products

@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return product

@router.post("/products", response_model=ProductOut, status_code=201)
async def create_product(product: ProductCreate, db: AsyncSession = Depends(get_db)):
    new_product = Product(**product.dict())
    db.add(new_product)
    await db.commit()
    await db.refresh(new_product)
    return new_product

@router.put("/products/{product_id}", response_model=ProductOut)
async def update_product(product_id: int, product: ProductUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    db_product = result.scalar_one_or_none()
    if not db_product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    for key, value in product.dict(exclude_unset=True).items():
        setattr(db_product, key, value)
    await db.commit()
    await db.refresh(db_product)
    return db_product

@router.delete("/products/{product_id}", status_code=204)
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    db_product = result.scalar_one_or_none()
    if not db_product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    await db.delete(db_product)
    await db.commit()
    return

# CATEGORÍAS
@router.get("/category", response_model=List[CategoryOut])
async def get_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category))
    categories = result.scalars().all()
    return categories

@router.get("/category/{category_id}", response_model=CategoryOut)
async def get_category(category_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    return category

@router.post("/category", response_model=CategoryOut, status_code=201)
async def create_category(category: CategoryCreate, db: AsyncSession = Depends(get_db)):
    new_category = Category(**category.dict())
    db.add(new_category)
    await db.commit()
    await db.refresh(new_category)
    return new_category

@router.put("/category/{category_id}", response_model=CategoryOut)
async def update_category(category_id: int, category: CategoryUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).where(Category.id == category_id))
    db_category = result.scalar_one_or_none()
    if not db_category:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    for key, value in category.dict(exclude_unset=True).items():
        setattr(db_category, key, value)
    await db.commit()
    await db.refresh(db_category)
    return db_category

@router.delete("/category/{category_id}", status_code=204)
async def delete_category(category_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).where(Category.id == category_id))
    db_category = result.scalar_one_or_none()
    if not db_category:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    await db.delete(db_category)
    await db.commit()
    return
