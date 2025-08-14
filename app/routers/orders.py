from fastapi import APIRouter, Depends, HTTPException, status, Request, File, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from app.database import get_db
from app.models.orders import Order, OrderItem
from app.models.product import Product, ProductImage
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import uuid
from pathlib import Path
import anyio
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

router = APIRouter()

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}

# ---------- Helpers ----------

def format_product_for_order(product: Product, db_images: Optional[List[ProductImage]] = None) -> Dict[str, Any]:
    images = getattr(product, "images", None) or db_images or []
    imagenes_ordenadas = sorted(images, key=lambda x: (not getattr(x, "is_main", False), getattr(x, "created_at", None))) if images else []
    imagenes_formateadas = [
        {
            "id": img.id,
            "secure_url": img.image_url,
            "public_id": f"temp_{img.id}",
            "main": img.is_main,
            "created_at": img.created_at.isoformat() if img.created_at else None
        } for img in imagenes_ordenadas
    ]
    return {
        "id": product.id,
        "name": product.name,
        "precio": float(product.price) if product.price is not None else None,
        "imagen": imagenes_formateadas,
        "descripcion": product.description,
        "stock": getattr(product, "stock", None),
        "category": getattr(product, "category_id", None),
    }

async def upload_to_supabase_storage(file: UploadFile, prefix: str = "orders") -> str:
    file_ext = Path(file.filename).suffix.lower() if file.filename else ""
    if file_ext not in ALLOWED_EXT:
        raise HTTPException(status_code=406, detail="Únicamente las extensiones de tipo jpg, jpeg, png y webp están permitidos")

    file_content = await file.read()
    file_name = f"{prefix}/{uuid.uuid4()}{file_ext}"

    def sync_upload():
        res = supabase.storage.from_("productimages").upload(path=file_name, file=file_content, file_options={"content-type": file.content_type or "application/octet-stream", "x-upsert": "true"})
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
            raise Exception(f"No se pudo obtener URL pública de Supabase. {err_msg or ''}")
        return url

    url = await anyio.to_thread.run_sync(sync_upload)
    return url

async def build_order_items_response(db: AsyncSession) -> List[Dict[str, Any]]:
    orders_q = await db.execute(select(Order).order_by(Order.created_at.desc()))
    orders = orders_q.scalars().all()
    result = []

    for order in orders:
        items = getattr(order, "items", []) or []
        for item in items:
            prod = None
            if hasattr(item, "product") and getattr(item, "product") is not None:
                prod = getattr(item, "product")
            else:
                prod_q = await db.execute(select(Product).where(Product.id == item.product_id))
                prod = prod_q.scalar_one_or_none()

            prod_images = []
            if prod is not None:
                if getattr(prod, "images", None):
                    prod_images = prod.images
                else:
                    imgs_q = await db.execute(select(ProductImage).where(ProductImage.product_id == prod.id))
                    prod_images = imgs_q.scalars().all()

            id_producto_obj = format_product_for_order(prod, prod_images) if prod else None

            id_orden_obj = {
                "nombre": getattr(order, "nombre", None),
                "apellido": getattr(order, "apellido", None),
                "email": getattr(order, "email", None),
                "telefono": getattr(order, "telefono", None),
                "direccion": getattr(order, "direccion", None),
                "descripcion": getattr(order, "descripcion", None),
                "image_transaccion": None
            }
            img_tx = getattr(order, "image_transaccion", None) or getattr(order, "transfer_image_url", None) or getattr(order, "voucher_url", None)
            if img_tx:
                if isinstance(img_tx, str):
                    id_orden_obj["image_transaccion"] = {"secure_url": img_tx}
                elif isinstance(img_tx, dict) and ("secure_url" in img_tx or "url" in img_tx):
                    id_orden_obj["image_transaccion"] = img_tx
                else:
                    id_orden_obj["image_transaccion"] = {"secure_url": str(img_tx)}

            fila = {
                "id": order.id,
                "fecha": order.created_at.isoformat() if getattr(order, "created_at", None) else None,
                "status": order.status,
                "id_producto": id_producto_obj,
                "id_orden": id_orden_obj,
                "talla": getattr(item, "talla", None),
                "color": getattr(item, "color", None),
                "cantidad": getattr(item, "quantity", None),
                "precio": float(getattr(item, "price", 0)) if getattr(item, "price", None) is not None else None,
                "order_item_id": item.id
            }
            result.append(fila)
    return result

# ---------- Endpoints ----------

# LISTADO (plural) - estructura ya conocida por frontend/admin
@router.get("/orders")
async def get_orders(db: AsyncSession = Depends(get_db)):
    try:
        filas = await build_order_items_response(db)
        return JSONResponse(content={"detail":[{"result": filas}]}, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener pedidos: {str(e)}")

# ALIAS: permitir también /order (singular) para compatibilidad
@router.get("/order")
async def get_orders_alias(db: AsyncSession = Depends(get_db)):
    return await get_orders(db)

# Obtener un pedido por id (plural)
@router.get("/orders/{order_id}")
async def get_order(order_id: int, db: AsyncSession = Depends(get_db)):
    try:
        order_q = await db.execute(select(Order).where(Order.id == order_id))
        order = order_q.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")

        filas = []
        items = getattr(order, "items", []) or []
        for item in items:
            prod_q = await db.execute(select(Product).where(Product.id == item.product_id))
            prod = prod_q.scalar_one_or_none()
            prod_imgs_q = await db.execute(select(ProductImage).where(ProductImage.product_id == prod.id)) if prod else None
            prod_imgs = prod_imgs_q.scalars().all() if prod_imgs_q else []
            filas.append({
                "id": order.id,
                "fecha": order.created_at.isoformat() if getattr(order, "created_at", None) else None,
                "status": order.status,
                "id_producto": format_product_for_order(prod, prod_imgs) if prod else None,
                "id_orden": {
                    "nombre": getattr(order, "nombre", None),
                    "apellido": getattr(order, "apellido", None),
                    "email": getattr(order, "email", None),
                    "telefono": getattr(order, "telefono", None),
                    "direccion": getattr(order, "direccion", None),
                    "descripcion": getattr(order, "descripcion", None),
                    "image_transaccion": ({"secure_url": getattr(order, "image_transaccion")}) if getattr(order, "image_transaccion", None) else None
                },
                "talla": getattr(item, "talla", None),
                "color": getattr(item, "color", None),
                "cantidad": getattr(item, "quantity", None),
                "precio": float(getattr(item, "price", 0)) if getattr(item, "price", None) is not None else None,
                "order_item_id": item.id
            })
        return JSONResponse(content={"detail":[{"result": filas}]}, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener pedido: {str(e)}")

@router.get("/order/{order_id}")
async def get_order_alias(order_id: int, db: AsyncSession = Depends(get_db)):
    return await get_order(order_id, db)

@router.post("/order", status_code=201)
async def create_order(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        content_type = (request.headers.get("content-type") or "").lower()
        is_multipart = "multipart/form-data" in content_type

        payload = {}
        transfer_image: Optional[UploadFile] = None

        if is_multipart:
            form = await request.form()
            data_raw = form.get("data") or "{}"
            try:
                payload = json.loads(data_raw)
            except json.JSONDecodeError:
                payload = {}
            transfer_image = form.get("transfer_image")
            if transfer_image and hasattr(transfer_image, "filename"):
                try:
                    url = await upload_to_supabase_storage(transfer_image, prefix=f"orders/{payload.get('user_id', 'temp')}")
                    payload["image_transaccion"] = url
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Error al subir imagen: {str(e)}")
        else:
            try:
                payload = await request.json()
            except json.JSONDecodeError:
                payload = {}

        required_fields = ["user_id", "price_order", "products"]
        if not all(field in payload for field in required_fields):
            raise HTTPException(status_code=400, detail="Datos incompletos para crear el pedido")

        async with db.begin():
            new_order = Order(
                user_id=int(payload["user_id"]),
                total=float(payload["price_order"]),
                status="pendiente"
            )
            for field in ["nombre", "apellido", "direccion", "email", "telefono", "descripcion"]:
                if field in payload:
                    setattr(new_order, field, payload[field])
            if "image_transaccion" in payload:
                new_order.image_transaccion = payload["image_transaccion"]

            db.add(new_order)
            await db.flush()

            for product in payload["products"]:
                product_id = product.get("id_producto") or product.get("id")
                if not product_id:
                    continue
                result = await db.execute(select(Product).where(Product.id == int(product_id)))
                db_product = result.scalar_one_or_none()
                if not db_product:
                    continue
                item = OrderItem(
                    order_id=new_order.id,
                    product_id=int(product_id),
                    quantity=int(product.get("cantidad", 1)),
                    price=float(db_product.price)
                )
                if "talla" in product:
                    item.talla = product["talla"]
                if "color" in product:
                    item.color = product["color"]
                db.add(item)

        # construimos respuesta (filas del pedido creado)
        filas = await build_order_items_response(db)
        filas_nuevo = [f for f in filas if f["id"] == new_order.id]
        return JSONResponse(content={"detail":[{"result": filas_nuevo}]}, status_code=201)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al crear pedido: {str(e)}")

# ACTUALIZAR estado/descr del pedido (se mantiene /orders/{id} porque frontend usa esa ruta)
@router.put("/orders/{order_id}")
async def update_order(order_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        payload = {}
        try:
            payload = await request.json()
        except Exception:
            try:
                form = await request.form()
                payload = dict(form)
            except Exception:
                payload = {}

        status_val = payload.get("status_order") or payload.get("status")
        descripcion = payload.get("descripcion") or payload.get("description") or payload.get("desc")

        q = await db.execute(select(Order).where(Order.id == order_id))
        order = q.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")

        if status_val is not None:
            order.status = status_val
        if descripcion is not None:
            try:
                setattr(order, "descripcion", descripcion)
            except Exception:
                pass

        await db.commit()
        await db.refresh(order)

        filas = await build_order_items_response(db)
        filas_order = [f for f in filas if f["id"] == order.id]
        return JSONResponse(content={"detail":[{"result": filas_order}]}, status_code=200)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al actualizar pedido: {str(e)}")

# ELIMINAR pedido (mantener /orders/{id})
@router.delete("/orders/{order_id}", status_code=204)
async def delete_order(order_id: int, db: AsyncSession = Depends(get_db)):
    try:
        q = await db.execute(select(Order).where(Order.id == order_id))
        order = q.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")

        try:
            await db.execute(delete(OrderItem).where(OrderItem.order_id == order_id))
        except Exception:
            pass

        await db.delete(order)
        await db.commit()
        return JSONResponse(status_code=204, content=None)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al eliminar pedido: {str(e)}")
