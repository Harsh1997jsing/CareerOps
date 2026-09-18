"""Declarative base shared by every CareerOps ORM model."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
