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

app = FastAPI(
    title="Saturnina API",
    description="API del backend de Saturnina",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://saturnina.vercel.app", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)


# Autenticación
app.include_router(auth.router, tags=["Autenticación"])

# Endpoints Públicos
app.include_router(user_public_router, tags=["Público"])

# Endpoints de Usuario
app.include_router(user.router, tags=["Usuarios"])
app.include_router(orders_router.router, tags=["Usuarios"])
app.include_router(comments.router, tags=["Usuarios"])

# Endpoints de Administrador
app.include_router(category.router, tags=["Administración"])
app.include_router(products.router, tags=["Administración"])


@app.get("/", tags=["General"])
def root():
    return {"message": "Saturnina Backend API"}

@app.get("/test-db", tags=["General"])
async def test_db_connection(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"success": True, "message": "Conexión exitosa a la base de datos"}
    except SQLAlchemyError as e:
        return {"success": False, "error": str(e)}
