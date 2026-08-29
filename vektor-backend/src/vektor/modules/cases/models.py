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

from sqlalchemy import String, and_, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vektor.core.database import Base
from vektor.shared.enums import UserRole

if TYPE_CHECKING:
    from vektor.modules.users.models import User


# Условия для фильтрующих проекций ниже. Функциями, а не строками, из-за
# ловушки: в строковом primaryjoin имя `Case` разрешается НЕ в эту модель, а в
# sqlalchemy.sql.elements.Case (конструкция SQL CASE — она живёт в том же
# пространстве имён, что подставляет SQLAlchemy), и конфигурация мапперов
# падает с «Class 'sqlalchemy.sql.elements.Case' is not mapped». У SchoolClass
# такого не было — там имена с sqlalchemy не пересекаются.
#
# Импорт User внутри функции, а не наверху модуля: вызов происходит уже после
# того, как все модели загружены, поэтому цикл импортов не возникает ни в
# какую сторону.
def _members_with_role(role: UserRole):
    def condition():
        from vektor.modules.users.models import User

        return and_(Case.id == User.case_id, User.role == role)

    return condition


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True)

    # unique прямо на колонке, без дублирующего UniqueConstraint в
    # __table_args__: для одной колонки это одно и то же, а два объявления
    # уехали бы в БД двумя одинаковыми индексами.
    name: Mapped[str] = mapped_column(String(255), unique=True)

    description: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    members: Mapped[list["User"]] = relationship(back_populates="case")

    students: Mapped[list["User"]] = relationship(
        primaryjoin=_members_with_role(UserRole.STUDENT),
        viewonly=True,
    )

    teachers: Mapped[list["User"]] = relationship(
        primaryjoin=_members_with_role(UserRole.TEACHER),
        viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<Case id={self.id} name={self.name}>"
