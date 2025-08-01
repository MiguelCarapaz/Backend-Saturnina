from sqlalchemy import Column, Integer, String, Text, Boolean
from app.database import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<Category {self.name}>"