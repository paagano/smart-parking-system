from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.mixins.timestamp import TimestampMixin


class BaseModel(Base, TimestampMixin):
    """
    Abstract base model inherited by all database entities.
    """

    __abstract__ = True

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
    )