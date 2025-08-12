from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete, update
from app.database import get_db
from app.models.product import Product, ProductImage, ProductSize, ProductColor
from app.models.category import Category
from typing import List, Optional
from pydantic import BaseModel
from fastapi.responses import JSONResponse, Response
from datetime import datetime
from sqlalchemy.orm import joinedload
import json
import anyio
import uuid
from pathlib import Path
from supabase import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# Configuración Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ====================== PYDANTIC / SCHEMAS ======================

class ImageSchema(BaseModel):
    id: Optional[int] = None
    image_url: str
    is_main: bool = False

class SizeSchema(BaseModel):
    name: str

class ColorSchema(BaseModel):
    name: str

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

# ====================== HELPERS ======================

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Producto no encontrado")
    return product

def format_product_response(product: Product):
    imagenes_ordenadas = sorted(
        product.images,
        key=lambda x: (not x.is_main, x.created_at)
    ) if product.images else []

    imagenes_formateadas = [
        {
            "id": img.id,
            "secure_url": img.image_url,
            "public_id": f"temp_{img.id}",
            "main": img.is_main,
            "created_at": img.created_at.isoformat() if img.created_at else None
        } for img in imagenes_ordenadas
    ]

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
        "category": product.category_id,
        "stock": product.stock,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "updated_at": product.updated_at.isoformat() if product.updated_at else None
    }

async def upload_to_supabase_storage(file: UploadFile, product_id: int) -> str:
    """
    Sube el contenido del UploadFile a Supabase Storage usando un thread para evitar
    I/O bloqueante dentro del loop async (evita el error greenlet_spawn).
    Retorna la URL pública (string).
    """
    try:
        file_ext = Path(file.filename).suffix or ""
        file_name = f"{product_id}_{uuid.uuid4()}{file_ext}"

        file_content = await file.read()

        # función sincrónica que ejecuta la subida y obtiene la URL
        def sync_upload_and_get_url():
            # Subida síncrona a Supabase
            res = supabase.storage.from_("productimages").upload(
                path=file_name,
                file=file_content,
                file_options={
                    "content-type": file.content_type or "application/octet-stream",
                    "x-upsert": "true"
                }
            )
            public = supabase.storage.from_("productimages").get_public_url(file_name)

            if isinstance(public, dict):
                url = public.get("publicUrl") or public.get("public_url") or public.get("url")
            else:
                url = public

            if not url:
                err_msg = None
                try:
                    if hasattr(res, "error") and res.error:
                        err_msg = getattr(res.error, "message", str(res.error))
                except Exception:
                    err_msg = None
                raise Exception(f"No se pudo obtener URL pública (supabase). {err_msg or ''}")
            return url

        url = await anyio.to_thread.run_sync(sync_upload_and_get_url)
        return url

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al subir imagen: {str(e)}"
        )
    

async def extract_files_from_form(form, keys: List[str]) -> List[UploadFile]:
    """Dado un FormData y una lista de posibles keys, devuelve lista de UploadFile encontradas."""
    files: List[UploadFile] = []
    for key in keys:
        try:
            list_files = form.getlist(key)
        except Exception:
            list_files = []
        for f in list_files:
            if hasattr(f, "filename"):
                files.append(f)
    return files

# ====================== ENDPOINTS ======================

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
async def create_product(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Crea un producto. Soporta:
      - multipart/form-data con campos: nombre_producto, id_categoria, descripcion, precio, stock, tallas (JSON string), colores (JSON string)
        + archivos en keys como 'imagenes_producto', 'imagen_producto', 'files', 'images'
      - application/json con un body JSON que tenga: nombre_producto, id_categoria, descripcion, precio, stock, tallas (list), colores (list)
        + en formato JSON no se admiten archivos (subir imágenes vía endpoint /products/{id}/images)
    """
    try:
        content_type = request.headers.get("content-type", "")
        is_multipart = "multipart/form-data" in content_type.lower()

        # Default values
        nombre_producto = None
        id_categoria_raw = None
        descripcion = None
        precio = None
        stock = 0
        tallas_list = []
        colores_list = []
        files: List[UploadFile] = []

        if is_multipart:
            form = await request.form()
            # extraer campos de form (puede venir como campo 'data' con JSON string)
            if "data" in form:
                # frontend sometimes sends a 'data' JSON string
                try:
                    payload = json.loads(form.get("data"))
                except Exception:
                    raise HTTPException(status_code=400, detail="Campo 'data' no es JSON válido")
                nombre_producto = payload.get("nombre_producto") or payload.get("name")
                id_categoria_raw = payload.get("id_categoria") or payload.get("category")
                descripcion = payload.get("descripcion") or payload.get("description")
                precio = payload.get("precio") or payload.get("price")
                stock = payload.get("stock", 0)
                tallas_list = payload.get("tallas", []) or []
                colores_list = payload.get("colores", []) or []
            else:
                nombre_producto = form.get("nombre_producto") or form.get("name")
                id_categoria_raw = form.get("id_categoria") or form.get("category")
                descripcion = form.get("descripcion") or form.get("description")
                precio = form.get("precio")
                stock = form.get("stock", 0)
                tallas_raw = form.get("tallas") or "[]"
                colores_raw = form.get("colores") or "[]"
                # parse tallas/colores si vienen como JSON strings
                try:
                    tallas_list = json.loads(tallas_raw) if isinstance(tallas_raw, str) else tallas_raw
                except Exception:
                    tallas_list = []
                try:
                    colores_list = json.loads(colores_raw) if isinstance(colores_raw, str) else colores_raw
                except Exception:
                    colores_list = []

            # extraer archivos en varias keys posibles
            def extract_list_from_form(f, key):
                try:
                    return f.getlist(key)
                except Exception:
                    # starlette FormData a veces no tiene getlist — fallback
                    v = f.get(key)
                    return [v] if v and hasattr(v, "filename") else []

            # keys posibles usadas en el frontend
            files = []
            for k in ("imagenes_producto", "imagen_producto", "files", "images", "nuevas_imagenes"):
                try:
                    lst = form.getlist(k)
                except Exception:
                    lst = []
                for el in lst:
                    if hasattr(el, "filename"):
                        files.append(el)

        else:
            # JSON body
            payload = await request.json()
            nombre_producto = payload.get("nombre_producto") or payload.get("name")
            id_categoria_raw = payload.get("id_categoria") or payload.get("category")
            descripcion = payload.get("descripcion") or payload.get("description")
            precio = payload.get("precio") or payload.get("price")
            stock = payload.get("stock", 0)
            tallas_list = payload.get("tallas", []) or []
            colores_list = payload.get("colores", []) or []
            files = []  # no hay archivos en JSON

        # Validaciones básicas de presencia
        if not nombre_producto:
            raise HTTPException(status_code=400, detail="nombre_producto es requerido")
        if id_categoria_raw is None:
            raise HTTPException(status_code=400, detail="id_categoria es requerido")
        if precio is None:
            raise HTTPException(status_code=400, detail="precio es requerido")

        # Normalizar id_categoria (acepta "category:1", "1" o 1)
        try:
            if isinstance(id_categoria_raw, str) and id_categoria_raw.startswith("category:"):
                category_id = int(id_categoria_raw.split(":")[1])
            else:
                category_id = int(id_categoria_raw)
        except Exception:
            raise HTTPException(status_code=400, detail="Formato inválido para id_categoria")

        # validar existencia de categoría
        cat_q = await db.execute(select(Category).where(Category.id == category_id))
        if not cat_q.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Categoría no encontrada")

        # validar imágenes (si vienen en multipart)
        if files and len(files) > 4:
            raise HTTPException(status_code=400, detail="No se pueden subir más de 4 imágenes por producto")

        # comprobar nombre único
        existing = await db.execute(select(Product).where(Product.name == nombre_producto))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Ya existe un producto con este nombre")

        # crear producto
        new_product = Product(
            name=nombre_producto,
            description=descripcion,
            price=float(precio),
            category_id=category_id,
            stock=int(stock)
        )
        db.add(new_product)
        await db.flush()  # para obtener id

        # subir imágenes si vienen
        for i, img in enumerate(files[:4]):
            url = await upload_to_supabase_storage(img, new_product.id)
            db.add(ProductImage(product_id=new_product.id, image_url=url, is_main=(i == 0)))

        # tallas y colores (soporta dicts o strings)
        for talla in tallas_list:
            if isinstance(talla, dict):
                name = talla.get("name")
            else:
                name = str(talla)
            if name:
                db.add(ProductSize(product_id=new_product.id, name=name))

        for color in colores_list:
            if isinstance(color, dict):
                name = color.get("name")
            else:
                name = str(color)
            if name:
                db.add(ProductColor(product_id=new_product.id, name=name))

        await db.commit()
        await db.refresh(new_product)

        return JSONResponse(content={"detail": format_product_response(new_product)}, status_code=201)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear producto: {str(e)}")

@router.put("/products/{product_id}", response_class=JSONResponse)
async def update_product(product_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Actualiza un producto. Si llegan nuevas imágenes en form-data (keys:
    'imagenes_producto', 'imagen_producto', 'nuevas_imagenes', 'images', 'files'),
    se ELIMINAN todas las imágenes actuales del producto (DB + Supabase) y
    se SUBEN las nuevas (reemplazo completo). Límite: 4 imágenes.
    """
    try:
        form = await request.form()
        data_raw = form.get("data") or form.get("producto") or "{}"
        try:
            product_data = json.loads(data_raw)
            product_update = ProductUpdate(**product_data)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON data")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Datos inválidos: {str(e)}")

        # obtener producto con imágenes/tallas/colores
        product = await get_product_or_404(db, product_id)

        # extraer archivos nuevos de posibles keys
        nuevas_imagenes = await extract_files_from_form(form, ["imagenes_producto", "imagen_producto", "nuevas_imagenes", "images", "files"])

        # Si hay nuevas imágenes -> reemplazo completo
        if nuevas_imagenes:
            if len(nuevas_imagenes) > 4:
                raise HTTPException(status_code=400, detail="No se pueden subir más de 4 imágenes por producto")

            # Traer imágenes actuales
            existing_q = await db.execute(select(ProductImage).where(ProductImage.product_id == product_id))
            existing_images = existing_q.scalars().all()

            # Eliminar archivos antiguos en Supabase (no romper si falla)
            for img in existing_images:
                try:
                    file_name = img.image_url.split('?')[0].split('/')[-1]
                    if file_name:
                        supabase.storage.from_("productimages").remove([file_name])
                except Exception as e:
                    print(f"Warning: no pude eliminar archivo supabase {getattr(img,'image_url',None)}: {e}")

            # Borrar filas de imágenes en DB
            await db.execute(delete(ProductImage).where(ProductImage.product_id == product_id))
            await db.commit()  # commit para que la DB refleje que ya no hay imágenes
            # refrescar la entidad producto para que product.images refleje el estado actual
            await db.refresh(product)

            # Subir nuevas imágenes y crear filas
            for i, imagen in enumerate(nuevas_imagenes[:4]):
                image_url = await upload_to_supabase_storage(imagen, product_id)
                is_main_flag = (i == 0)
                db.add(ProductImage(product_id=product_id, image_url=image_url, is_main=is_main_flag))

        # Si en JSON vienen imágenes con ids -> actualizar is_main según lo enviado
        if product_update.images is not None:
            for img_data in product_update.images:
                if getattr(img_data, "id", None) is not None:
                    await db.execute(
                        update(ProductImage)
                        .where(ProductImage.id == img_data.id)
                        .values(is_main=bool(img_data.is_main))
                    )

        # Reemplazar tallas si vienen
        if product_update.tallas is not None:
            await db.execute(delete(ProductSize).where(ProductSize.product_id == product_id))
            for talla in product_update.tallas:
                db.add(ProductSize(product_id=product_id, name=talla.name))

        # Reemplazar colores si vienen
        if product_update.colores is not None:
            await db.execute(delete(ProductColor).where(ProductColor.product_id == product_id))
            for color in product_update.colores:
                db.add(ProductColor(product_id=product_id, name=color.name))

        # Actualizar otros campos
        if product_update.nombre_producto:
            product.name = product_update.nombre_producto
        if product_update.descripcion:
            product.description = product_update.descripcion
        if product_update.precio is not None:
            product.price = product_update.precio
        if product_update.stock is not None:
            product.stock = product_update.stock
        if product_update.id_categoria:
            cid = product_update.id_categoria
            if isinstance(cid, str) and cid.startswith("category:"):
                product.category_id = int(cid.split(":")[1])
            else:
                product.category_id = int(cid)

        product.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(product)

        return JSONResponse(content={"detail": format_product_response(product)}, status_code=200)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error inesperado al actualizar producto: {str(e)}")

@router.delete("/products/{product_id}", status_code=204)
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db)):
    try:
        images = await db.execute(select(ProductImage).where(ProductImage.product_id == product_id))
        images = images.scalars().all()
        for img in images:
            try:
                file_name = img.image_url.split('?')[0].split('/')[-1]
                if file_name:
                    supabase.storage.from_("productimages").remove([file_name])
            except Exception as e:
                print(f"Error al eliminar imagen de Supabase: {str(e)}")

        product = await get_product_or_404(db, product_id)
        await db.delete(product)
        await db.commit()
        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al eliminar producto: {str(e)}")

# Endpoints específicos para imágenes

@router.post("/products/{product_id}/images", status_code=201)
async def add_product_images(product_id: int, images: List[UploadFile] = File(...), db: AsyncSession = Depends(get_db)):
    try:
        product = await get_product_or_404(db, product_id)
        result = await db.execute(select(ProductImage).where(ProductImage.product_id == product_id))
        current_images = result.scalars().all()
        if len(current_images) + len(images) > 4:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"No se pueden tener más de 4 imágenes. Actual: {len(current_images)}, Intentando agregar: {len(images)}")
        for image in images:
            image_url = await upload_to_supabase_storage(image, product_id)
            db.add(ProductImage(product_id=product_id, image_url=image_url, is_main=False))
        await db.commit()
        return JSONResponse(content={"detail": "Imágenes agregadas correctamente"}, status_code=201)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al agregar imágenes: {str(e)}")

@router.delete("/products/{product_id}/images/{image_id}", status_code=204)
async def delete_product_image(product_id: int, image_id: int, db: AsyncSession = Depends(get_db)):
    try:
        await get_product_or_404(db, product_id)
        result = await db.execute(select(ProductImage).where(ProductImage.id == image_id, ProductImage.product_id == product_id))
        image = result.scalar_one_or_none()
        if not image:
            raise HTTPException(status_code=404, detail="Imagen no encontrada para este producto")
        try:
            file_name = image.image_url.split('?')[0].split('/')[-1]
            if file_name:
                supabase.storage.from_("productimages").remove([file_name])
        except Exception as e:
            print(f"Error al eliminar imagen de Supabase: {str(e)}")
        await db.execute(delete(ProductImage).where(ProductImage.id == image_id, ProductImage.product_id == product_id))
        await db.commit()
        return Response(status_code=204)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al eliminar imagen: {str(e)}")

@router.patch("/products/{product_id}/images/{image_id}/set-main", status_code=200)
async def set_main_image(product_id: int, image_id: int, db: AsyncSession = Depends(get_db)):
    try:
        await get_product_or_404(db, product_id)
        result = await db.execute(select(ProductImage).where(ProductImage.id == image_id, ProductImage.product_id == product_id))
        image = result.scalar_one_or_none()
        if not image:
            raise HTTPException(status_code=404, detail="Imagen no encontrada para este producto")
        await db.execute(update(ProductImage).where(ProductImage.product_id == product_id).values(is_main=False))
        image.is_main = True
        db.add(image)
        await db.commit()
        return JSONResponse(content={"detail": "Imagen principal actualizada correctamente"}, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al actualizar imagen principal: {str(e)}")
