from fastapi import APIRouter

router = APIRouter(
    prefix="/example",
    tags=["example"]
)

@router.get("/")
async def example_endpoint():
    return {"message": "Este es un endpoint de ejemplo"}
