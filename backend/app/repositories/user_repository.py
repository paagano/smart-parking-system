from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    """
    Repository for User-specific database operations.
    """

    def __init__(self):
        super().__init__(User)

    def get_by_email(
        self,
        db: Session,
        email: str,
    ) -> User | None:
        return (
            db.query(User)
            .filter(User.email == email)
            .first()
        )

    def get_by_phone(
        self,
        db: Session,
        phone_number: str,
    ) -> User | None:
        return (
            db.query(User)
            .filter(User.phone_number == phone_number)
            .first()
        )
