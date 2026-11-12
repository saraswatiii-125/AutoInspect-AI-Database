from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class InspectionModel(Base):
    __tablename__ = "inspections"

    id = Column(String, primary_key=True, index=True)
    vehicle_id = Column(
        String,
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    date = Column(String, nullable=False)
    status = Column(String, default="completed")
    overall_score = Column(Integer, default=80)
    total_cost_min = Column(Integer, default=0)
    total_cost_max = Column(Integer, default=0)

    # JSON columns for nested structured data matching TypeScript contracts
    damages = Column(JSON, default=list)
    images = Column(JSON, default=list)
    ai_insights = Column(JSON, default=list)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Parent relationship back to vehicle
    vehicle = relationship("VehicleModel", back_populates="inspections")
