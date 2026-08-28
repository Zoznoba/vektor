"""Кейс — профильная группа (кружок), где ученики из РАЗНЫХ классов занимаются
под руководством 2–3 учителей. Нейминг школьный, поэтому «case», а не «group».

Ключевое отличие от класса: членство — ОДИН кейс и у ученика, и у учителя
(подтверждено заказчиком). Поэтому связь выражается обычным FK на users, а не
association object'ом вроде TeacherClass: «ровно один» лучше гарантировать
схемой, чем проверкой в сервисе. Одна колонка на обе роли — кто есть кто,
различается по User.role.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vektor.core.database import Base

if TYPE_CHECKING:
    from vektor.modules.users.models import User


class Case(Base):
    __tablename__ = "cases"

    __table_args__ = (
        UniqueConstraint("name")
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    
    name: str = mapped_column(String(255), nullable=False, unique=True)
    
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    
    members: Mapped[list["User"]] = relationship(
        "User",
        back_populates="case",
        cascade="all, delete-orphan",
    )

    students: Mapped[list["User"]] = relationship(
        "User", 
        back_populates ="case",
        primaryjoin="and_(Case.id == User.case_id, User.role == 'student')",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<Case id={self.id} name={self.name}>"
