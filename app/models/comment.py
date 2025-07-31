from sqlalchemy import Column, Integer, Text, ForeignKey, DateTime, CheckConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class Comment(Base):
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    rating = Column(Integer, CheckConstraint('rating >= 1 AND rating <= 5'))
    comment = Column(Text)
    created_at = Column(DateTime(timezone=False), server_default=func.now())
