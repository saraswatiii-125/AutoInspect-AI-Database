from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class VehicleModel(Base):
    __tablename__ = "vehicles"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    make = Column(String, nullable=False)
    model = Column(String, nullable=False)
    year = Column(Integer, nullable=False)
    registration = Column(String, nullable=False, unique=True, index=True)
    color = Column(String, nullable=False)
    image = Column(String, nullable=False)
    health_score = Column(Integer, default=100)
    latest_inspection_date = Column(String, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Cascading deletion: deleting a vehicle automatically deletes all associated inspections
    inspections = relationship(
        "InspectionModel",
        back_populates="vehicle",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
