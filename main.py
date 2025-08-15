from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from app.routers import auth, comments, user, products, category
from app.routers.user import router_public as user_public_router
from app.routers import orders as orders_router
from app.database import get_db
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

app = FastAPI()

# Configuración CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://saturnina.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Routers
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(user_public_router)
app.include_router(products.router)
app.include_router(category.router)
app.include_router(orders_router.router)
app.include_router(comments.router)

@app.api_route("/", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"])
def root():
    return {"message": "Saturnina Backend API"}

@app.get("/test-db")
async def test_db_connection(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"success": True, "message": "Conexión exitosa a la base de datos"}
    except SQLAlchemyError as e:
        return {"success": False, "error": str(e)}