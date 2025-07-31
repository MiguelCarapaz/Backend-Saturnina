from sqlalchemy import Column, Integer, String, Numeric, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    price = Column(Numeric, nullable=False)
    stock = Column(Integer, default=0)
    image_url = Column(Text)
    category_id = Column(Integer, ForeignKey("categories.id"))
