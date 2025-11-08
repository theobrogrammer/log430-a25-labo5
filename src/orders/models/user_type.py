"""
UserType class (value object)
SPDX - License - Identifier: LGPL - 3.0 - or -later
Auteurs : Gabriel C. Ullmann, Fabio Petrillo, 2025
"""

from sqlalchemy import Column, Integer, String
from orders.models.base import Base

class UserType(Base):
    __tablename__ = 'user_types'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)