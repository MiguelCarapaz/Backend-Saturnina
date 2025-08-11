from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from app.routers import example, auth, user, products, orders_comments, category
from app.routers.user import profile_router
from app.database import get_db
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# ✅ Dominios permitidos (Producción y Desarrollo)
origins = [
    "https://saturnina.vercel.app",  # Producción
    "http://localhost:3000",         # Local React dev
    "http://127.0.0.1:3000"          # Otra forma de local
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,      # Lista explícita de dominios
    allow_credentials=True,     # Para cookies y Authorization header
    allow_methods=["*"],        # Todos los métodos HTTP
    allow_headers=["*"],        # Todas las cabeceras
    expose_headers=["*"],       # Exponer cabeceras al frontend
)

# Routers
app.include_router(example.router)
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(profile_router)
app.include_router(products.router)
app.include_router(category.router)
app.include_router(orders_comments.router)

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
