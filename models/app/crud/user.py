"""
Database CRUD operations for the users table.
"""

from typing import Optional
from sqlalchemy.orm import Session
from app.models.user import UserModel


def get_user_by_email(db: Session, email: str) -> Optional[UserModel]:
    """
    Retrieves a user by their unique normalized email address.
    """
    return db.query(UserModel).filter(UserModel.email == email).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[UserModel]:
    """
    Retrieves a user by their integer primary key.
    """
    return db.query(UserModel).filter(UserModel.id == user_id).first()


def create_user(
    db: Session,
    email: str,
    hashed_password: str,
    role: str = "customer",
) -> UserModel:
    """
    Creates and persists a new user record in public.users.
    Role is strictly defaulted to 'customer'.
    """
    db_user = UserModel(
        email=email,
        hashed_password=hashed_password,
        role=role,
    )
    try:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    except Exception:
        db.rollback()
        raise

