from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from app.database import get_db
from app.models.orders import Order, OrderItem
from app.models.product import Product, ProductImage
from typing import List, Dict, Any, Optional
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


# ---------------- Helpers ----------------

def title_status(s: Optional[str]) -> Optional[str]:
    if not s:
        return s
    # convierte "pendiente" -> "Pendiente", "en entrega" -> "En entrega"
    return s.capitalize()

def format_product_for_order(product: Product, db_images: Optional[List[ProductImage]] = None) -> Dict[str, Any]:
    images = db_images or []
    imagenes_ordenadas = sorted(
        images,
        key=lambda x: (not getattr(x, "is_main", False), getattr(x, "created_at", None))
    ) if images else []
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

async def build_order_items_response_for_orders(orders: List[Order], db: AsyncSession) -> List[Dict[str, Any]]:
    """
    Construye filas (una por OrderItem) para una lista de orders provistas.
    Evita lazy loads; hace selects explícitos.
    """
    result: List[Dict[str, Any]] = []
    for order in orders:
        # items del pedido
        items_q = await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
        items = items_q.scalars().all()
        for item in items:
            # producto
            prod_q = await db.execute(select(Product).where(Product.id == item.product_id))
            prod = prod_q.scalar_one_or_none()

            prod_images = []
            if prod is not None:
                imgs_q = await db.execute(select(ProductImage).where(ProductImage.product_id == prod.id))
                prod_images = imgs_q.scalars().all()

            id_producto_obj = format_product_for_order(prod, prod_images) if prod else None

            # construir id_orden (meta) y top-level descripcion
            img_tx = getattr(order, "image_transaccion", None) or getattr(order, "transfer_image_url", None) or getattr(order, "voucher_url", None)
            image_obj = None
            if img_tx:
                if isinstance(img_tx, str):
                    image_obj = {"secure_url": img_tx}
                elif isinstance(img_tx, dict) and ("secure_url" in img_tx or "url" in img_tx):
                    image_obj = img_tx
                else:
                    image_obj = {"secure_url": str(img_tx)}

            id_orden_obj = {
                "id": order.id,
                "nombre": getattr(order, "nombre", None),
                "apellido": getattr(order, "apellido", None),
                "email": getattr(order, "email", None),
                "telefono": getattr(order, "telefono", None),
                "direccion": getattr(order, "direccion", None),
                "descripcion": getattr(order, "descripcion", None),
                "image_transaccion": image_obj
            }

            fila = {
                "id": order.id,
                "fecha": order.created_at.isoformat() if getattr(order, "created_at", None) else None,
                "status": title_status(order.status),
                "id_producto": id_producto_obj,
                "id_orden": id_orden_obj,
                "talla": getattr(item, "talla", None),
                "color": getattr(item, "color", None),
                "cantidad": getattr(item, "quantity", None),
                "precio": float(getattr(item, "price", 0)) if getattr(item, "price", None) is not None else None,
                "order_item_id": item.id,
                # campo top-level que el frontend usa en algunos lugares:
                "descripcion": getattr(order, "descripcion", None)
            }
            result.append(fila)
    return result

# ---------------- Endpoints ----------------

@router.get("/orders")
async def get_orders(db: AsyncSession = Depends(get_db)):
    """
    Devuelve todos los pedidos (filas) en el formato que el frontend/admin espera:
    {"detail":[{"result": [ ... filas ... ] }]}
    """
    try:
        orders_q = await db.execute(select(Order).order_by(Order.created_at.desc()))
        orders = orders_q.scalars().all()
        filas = await build_order_items_response_for_orders(orders, db)
        return JSONResponse(content={"detail":[{"result": filas}]}, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener pedidos: {str(e)}")

@router.get("/orders/{order_id}")
async def get_order_by_id(order_id: int, db: AsyncSession = Depends(get_db)):
    """
    Devuelve las filas (order items) correspondientes a UN pedido por su order.id
    """
    try:
        order_q = await db.execute(select(Order).where(Order.id == order_id))
        order = order_q.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")

        filas = await build_order_items_response_for_orders([order], db)
        return JSONResponse(content={"detail":[{"result": filas}]}, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener pedido: {str(e)}")

@router.get("/order/{user_id}")
async def get_orders_by_user(user_id: int, db: AsyncSession = Depends(get_db)):
    """
    Endpoint que usa el frontend de USUARIO: GET /order/{userId}
    Devuelve todas las filas (order items) de los pedidos creados por ese user_id.
    """
    try:
        orders_q = await db.execute(select(Order).where(Order.user_id == int(user_id)).order_by(Order.created_at.desc()))
        orders = orders_q.scalars().all()
        if not orders:
            # devolver array vacío (frontend espera estructura consistente)
            return JSONResponse(content={"detail":[{"result": []}]}, status_code=200)

        filas = await build_order_items_response_for_orders(orders, db)
        return JSONResponse(content={"detail":[{"result": filas}]}, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener pedidos del usuario: {str(e)}")

@router.post("/order", status_code=201)
async def create_order(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Crea pedido. Acepta multipart/form-data con:
      - data: JSON string con { user_id, price_order, products: [{id_producto, cantidad, talla, color}], nombre, apellido, direccion, email, telefono, descripcion }
      - transfer_image: archivo (jpg/jpeg/png/webp)
    También acepta application/json con el mismo objeto (sin archivo).
    """
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
            except Exception:
                payload = {}
            transfer_image = form.get("transfer_image")
            if transfer_image and hasattr(transfer_image, "filename"):
                url = await upload_to_supabase_storage(transfer_image, prefix=f"orders/{payload.get('user_id','temp')}")
                payload["image_transaccion"] = url
        else:
            try:
                payload = await request.json()
            except Exception:
                payload = {}

        user_id = payload.get("user_id") or payload.get("userId") or payload.get("user")
        price_order = payload.get("price_order") or payload.get("total") or payload.get("price")
        products = payload.get("products") or payload.get("items") or payload.get("productos") or []
        if user_id is None or price_order is None or not isinstance(products, list) or len(products) == 0:
            raise HTTPException(status_code=400, detail="Datos incompletos para crear el pedido")

        # Crear la orden en transacción
        async with db.begin():
            new_order = Order(user_id=int(user_id), total=float(price_order), status="pendiente")
            for key in ("nombre","apellido","direccion","email","telefono","descripcion"):
                if key in payload and payload.get(key) is not None:
                    try:
                        setattr(new_order, key, payload.get(key))
                    except Exception:
                        pass

            if "image_transaccion" in payload:
                try:
                    setattr(new_order, "image_transaccion", payload["image_transaccion"])
                except Exception:
                    pass

            db.add(new_order)
            await db.flush()

            for prod in products:
                prod_id = prod.get("id_producto") or prod.get("id") or prod.get("product_id")
                if not prod_id:
                    continue
                p_q = await db.execute(select(Product).where(Product.id == int(prod_id)))
                p_obj = p_q.scalar_one_or_none()
                price = float(p_obj.price) if p_obj and getattr(p_obj, "price", None) is not None else float(prod.get("precio") or prod.get("price") or 0)
                cantidad = prod.get("cantidad") or prod.get("quantity") or 1
                item = OrderItem(order_id=new_order.id, product_id=int(prod_id), quantity=int(cantidad), price=price)
                try:
                    if "talla" in prod and prod["talla"] is not None:
                        setattr(item, "talla", prod["talla"])
                except Exception:
                    pass
                try:
                    if "color" in prod and prod["color"] is not None:
                        setattr(item, "color", prod["color"])
                except Exception:
                    pass
                db.add(item)

        filas = await build_order_items_response_for_orders([new_order], db)
        filas_nuevo = [f for f in filas if f["id"] == new_order.id]
        return JSONResponse(content={"detail":[{"result": filas_nuevo}]}, status_code=201)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear pedido: {str(e)}")

@router.put("/order/{order_id}")
async def update_order_user(order_id: int, request: Request, db: AsyncSession = Depends(get_db)):
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
            except Exception:
                payload = {}
            transfer_image = form.get("transfer_image")
            if transfer_image and hasattr(transfer_image, "filename") and not transfer_image.filename:
                transfer_image = None
        else:
            try:
                payload = await request.json()
            except Exception:
                payload = {}

        q = await db.execute(select(Order).where(Order.id == order_id))
        order = q.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")

        if (order.status or "").lower() != "pendiente":
            raise HTTPException(status_code=400, detail="Solo se pueden editar pedidos con estado 'Pendiente'")

        if transfer_image:
            try:
                prefix = f"orders/{getattr(order, 'user_id', 'temp')}"
                url = await upload_to_supabase_storage(transfer_image, prefix=prefix)
                payload["image_transaccion"] = url
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error al subir imagen: {str(e)}")

        allowed = ("nombre", "apellido", "direccion", "email", "telefono", "descripcion", "image_transaccion")
        dirty = False
        for key in allowed:
            if key in payload and payload.get(key) is not None:
                try:
                    setattr(order, key, payload.get(key))
                    dirty = True
                except Exception:
                    pass

        if dirty:
            await db.commit()
            await db.refresh(order)
        else:
            await db.refresh(order)

        filas = await build_order_items_response_for_orders([order], db)
        filas_order = [f for f in filas if f["id"] == order.id]
        return JSONResponse(content={"detail":[{"result": filas_order}]}, status_code=200)

    except HTTPException:
        raise
    except Exception as e:
        try:
            await db.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Error al actualizar pedido: {str(e)}")

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
