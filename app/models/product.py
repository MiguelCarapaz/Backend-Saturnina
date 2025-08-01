from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    images = Column(JSONB)  # Almacena [{secure_url: "...", public_id: "..."}]
    category_id = Column(Integer, ForeignKey("categories.id"))
    stock = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<Product {self.name}>"