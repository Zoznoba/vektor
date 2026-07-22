from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vektor.core.database import Base
from vektor.shared.enums import UserRole

if TYPE_CHECKING:
    from vektor.modules.classes.models import SchoolClass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str]
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        # values_callable: хранить в БД значения ("student"), а не имена ("STUDENT") —
        # единый формат с API-контрактом и будущим импортом (Этап 6).
        Enum(UserRole, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e])
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    school_class_id: Mapped[int | None] = mapped_column(ForeignKey("school_classes.id"))
    school_class: Mapped["SchoolClass | None"] = relationship(back_populates="students")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"
