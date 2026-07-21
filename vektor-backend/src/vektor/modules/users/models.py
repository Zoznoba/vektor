from datetime import datetime

from sqlalchemy import Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from vektor.core.database import Base
from vektor.shared.enums import UserRole


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

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"
