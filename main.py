from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from app.routers import example, auth, user, products, orders_comments
from app.database import get_db
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://saturnina.vercel.app"],  # solo tu frontend en producción
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluye tus routers aquí
app.include_router(example.router)
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(products.router)
app.include_router(orders_comments.router)

@app.get("/")
def root():
    return {"message": "Saturnina Backend API"}

@app.get("/test-db")
async def test_db_connection(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"success": True, "message": "Conexión exitosa a la base de datos"}
    except SQLAlchemyError as e:
        return {"success": False, "error": str(e)}
