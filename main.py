from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from app.routers import example, auth, user, products, orders_comments, category
from app.database import get_db
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

origins = [
    "https://saturnina.vercel.app",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://saturnina.vercel.app/",
    "http://localhost:3000/",
    "http://127.0.0.1:3000/"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "Access-Control-Allow-Origin",
        "Access-Control-Allow-Headers",
        "Access-Control-Allow-Methods",
        "Access-Control-Allow-Credentials",
        "*"
    ],
    expose_headers=["*"],
    max_age=600
)

# Incluye tus routers aquí
app.include_router(example.router)
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(products.router)
app.include_router(category.router)
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
