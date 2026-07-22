from typing import Any, Generic, Type, TypeVar

from sqlalchemy.orm import Session

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    """
    Base repository providing common CRUD operations.
    """

    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get_by_id(
        self,
        db: Session,
        id: Any,
    ) -> ModelType | None:
        """
        Retrieve a record by its primary key.
        """
        return db.get(self.model, id)

    def get_all(
        self,
        db: Session,
    ) -> list[ModelType]:
        """
        Retrieve all records.
        """
        return db.query(self.model).all()

    def create(
        self,
        db: Session,
        obj: ModelType,
    ) -> ModelType:
        """
        Persist a new record.
        """
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def delete(
        self,
        db: Session,
        obj: ModelType,
    ) -> None:
        """
        Delete a record.
        """
        db.delete(obj)
        db.commit()