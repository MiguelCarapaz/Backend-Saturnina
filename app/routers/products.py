from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File
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
import json
import uuid
from pathlib import Path
from supabase import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# Configuración Supabase
import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
    nombre_producto: Optional[str] = None
    id_categoria: Optional[str] = None
    descripcion: Optional[str] = None
    precio: Optional[float] = None
    stock: Optional[int] = None
    tallas: Optional[List[SizeSchema]] = None
    colores: Optional[List[ColorSchema]] = None
    images: Optional[List[ImageSchema]] = None
    
    class Config:
        extra = "ignore"

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

async def upload_to_supabase_storage(file: UploadFile, product_id: int) -> str:
    """Sube un archivo a Supabase Storage y retorna la URL pública"""
    try:
        # Generar un nombre único para el archivo
        file_ext = Path(file.filename).suffix
        file_name = f"{product_id}_{uuid.uuid4()}{file_ext}"
        
        # Leer el contenido del archivo
        file_content = await file.read()
        
        # Subir a Supabase Storage
        res = supabase.storage.from_("productimages").upload(
            file_name,
            file_content,
            {"content-type": file.content_type}
        )
        
        # Obtener URL pública
        url = supabase.storage.from_("productimages").get_public_url(file_name)
        
        return url
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al subir la imagen: {str(e)}"
        )

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
async def create_product(
    nombre_producto: str = Form(...),
    id_categoria: str = Form(...),
    descripcion: Optional[str] = Form(None),
    precio: float = Form(...),
    stock: int = Form(0),
    tallas: str = Form("[]"),
    colores: str = Form("[]"),
    imagen_producto: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db)
):
    try:
        # Parsear los datos JSON de tallas y colores
        try:
            tallas_list = json.loads(tallas)
            colores_list = json.loads(colores)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Formato inválido para tallas o colores")
        
        # Convertir id_categoria a int
        if id_categoria.startswith("category:"):
            category_id = int(id_categoria.split(":")[1])
        else:
            raise HTTPException(status_code=400, detail="Formato inválido para id_categoria")

        # Verificar si la categoría existe
        category = await db.execute(select(Category).where(Category.id == category_id))
        if not category.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Categoría no encontrada")

        # Verificar si el producto ya existe
        existing_product = await db.execute(select(Product).where(Product.name == nombre_producto))
        if existing_product.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Ya existe un producto con este nombre")

        # Crear el producto
        new_product = Product(
            name=nombre_producto,
            description=descripcion,
            price=precio,
            category_id=category_id,
            stock=stock
        )
        db.add(new_product)
        await db.commit()
        await db.refresh(new_product)

        # Subir imagen si se proporcionó
        image_url = None
        if imagen_producto:
            image_url = await upload_to_supabase_storage(imagen_producto, new_product.id)
            db.add(ProductImage(
                product_id=new_product.id,
                image_url=image_url,
                is_main=True
            ))

        # Guardar tallas
        for talla in tallas_list:
            db.add(ProductSize(
                product_id=new_product.id,
                name=talla.get("name")
            ))

        # Guardar colores
        for color in colores_list:
            db.add(ProductColor(
                product_id=new_product.id,
                name=color.get("name")
            ))

        await db.commit()
        await db.refresh(new_product)

        return JSONResponse(content={"detail": format_product_response(new_product)}, status_code=201)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear producto: {str(e)}")

@router.put("/products/{product_id}", response_class=JSONResponse)
async def update_product(
    product_id: int,
    data: str = Form(...),
    imagen_producto: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db)
):
    try:
        # Parsear el JSON string a un diccionario
        try:
            product_data = json.loads(data)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON data")
        
        # Validar con el modelo Pydantic
        product_update = ProductUpdate(**product_data)
        
        # Obtener el producto
        product = await get_product_or_404(db, product_id)
        
        # Convertir id_categoria a int si es necesario
        if product_update.id_categoria and product_update.id_categoria.startswith("category:"):
            category_id = int(product_update.id_categoria.split(":")[1])
        else:
            category_id = product.category_id
        
        # Preparar datos de actualización
        update_data = {
            "name": product_update.nombre_producto or product.name,
            "description": product_update.descripcion or product.description,
            "price": product_update.precio or product.price,
            "category_id": category_id,
            "stock": product_update.stock or product.stock
        }
        
        # Procesar imagen si existe
        if imagen_producto:
            image_url = await upload_to_supabase_storage(imagen_producto, product_id)
            await db.execute(delete(ProductImage).where(ProductImage.product_id == product_id))
            db.add(ProductImage(
                product_id=product_id,
                image_url=image_url,
                is_main=True
            ))
        # O si se enviaron URLs de imágenes directamente
        elif product_update.images is not None:
            await db.execute(delete(ProductImage).where(ProductImage.product_id == product_id))
            for img in product_update.images:
                db.add(ProductImage(
                    product_id=product_id,
                    image_url=img.image_url,
                    is_main=img.is_main
                ))
        
        # Actualizar tallas si se enviaron
        if product_update.tallas is not None:
            await db.execute(delete(ProductSize).where(ProductSize.product_id == product_id))
            for talla in product_update.tallas:
                db.add(ProductSize(
                    product_id=product_id,
                    name=talla.name
                ))
        
        # Actualizar colores si se enviaron
        if product_update.colores is not None:
            await db.execute(delete(ProductColor).where(ProductColor.product_id == product_id))
            for color in product_update.colores:
                db.add(ProductColor(
                    product_id=product_id,
                    name=color.name
                ))
        
        # Actualizar campos del producto
        for field, value in update_data.items():
            setattr(product, field, value)
        
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
        # Primero eliminar las imágenes asociadas en Supabase Storage
        images = await db.execute(select(ProductImage).where(ProductImage.product_id == product_id))
        images = images.scalars().all()
        
        for img in images:
            try:
                # Extraer el nombre del archivo de la URL
                file_name = img.image_url.split('/')[-1]
                supabase.storage.from_("productimages").remove([file_name])
            except Exception as e:
                print(f"Error al eliminar imagen de Supabase: {str(e)}")
        
        # Luego eliminar el producto y sus relaciones en la base de datos
        product = await get_product_or_404(db, product_id)
        await db.delete(product)
        await db.commit()
        
        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al eliminar producto: {str(e)}")