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

    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False, length=20))

    is_active: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"
