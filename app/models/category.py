from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship  
from app.database import Base
from datetime import datetime

class Category(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    products = relationship("Product", back_populates="category")