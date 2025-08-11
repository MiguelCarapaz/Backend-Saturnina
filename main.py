from fastapi import FastAPI, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text
from app.routers import example, auth, user, products, orders_comments, category
from app.routers.user import profile_router
from app.database import get_db
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# ✅ Dominios permitidos
origins = [
    "https://saturnina.vercel.app",  # Producción
    "http://localhost:3000",         # Local React dev
    "http://127.0.0.1:3000"          # Otra forma de local
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# 📌 Middleware para registrar cada request (debug CORS y Auth)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"\n🔹 Nueva petición:")
    print(f"   Método: {request.method}")
    print(f"   URL: {request.url}")
    print(f"   Origen: {request.headers.get('origin')}")
    print(f"   Authorization: {request.headers.get('authorization')}")
    print(f"   Content-Type: {request.headers.get('content-type')}")
    
    response = await call_next(request)
    
    print(f"   ↩ Status: {response.status_code}")
    print(f"   ↩ CORS Headers: {response.headers.get('access-control-allow-origin')}")
    return response

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
