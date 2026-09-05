from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Enum, ForeignKey, Integer, String, Table, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vektor.core.database import Base

# Case импортируется НА РАНТАЙМЕ, а не под TYPE_CHECKING, в отличие от
# SchoolClass ниже. Причина — коллизия имён: аннотацию Mapped["Case | None"]
# SQLAlchemy разрешает строкой, и без настоящего Case в пространстве имён
# модуля она находит sqlalchemy.sql.elements.Case (конструкция SQL CASE),
# после чего конфигурация мапперов падает с «Class
# 'sqlalchemy.sql.elements.Case' is not mapped». Цикла импортов это не
# создаёт: cases/models.py тянет users только лениво, внутри функции.
from vektor.modules.cases.models import Case
from vektor.shared.enums import UserRole

if TYPE_CHECKING:
    from vektor.modules.classes.models import SchoolClass

# Association table «родитель — ребёнок». Оба FK смотрят в ОДНУ И ТУ ЖЕ таблицу
# users — в отличие от teacher_classes (там связь шла в две разные таблицы, и
# SQLAlchemy сама разбиралась, какой FK к какой стороне относится). Здесь такой
# автоматики нет: без явных primaryjoin/secondaryjoin в relationship SQLAlchemy
# не поймёт, где «я родитель», а где «я ребёнок».
parent_children = Table(
    "parent_children",
    Base.metadata,
    Column("parent_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("child_id", Integer, ForeignKey("users.id"), primary_key=True),
)


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

    # Служебный респондент-заглушка, а не человек: в выгрузке МО педагоги и
    # родители обезличены, и на каждый слот (класс, роль, номер) заводится одна
    # учётка. server_default обязателен — колонка NOT NULL, и без него уже
    # существующие строки не проходят миграцию; заодно совпадает с DDL дампа,
    # иначе autogenerate вечно видел бы расхождение. См. b9d41f7c2a08.
    is_placeholder: Mapped[bool] = mapped_column(default=False, server_default=false())

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # foreign_keys обязателен: после появления school_classes.homeroom_teacher_id
    # между users и school_classes ДВА пути по FK, и SQLAlchemy сама не угадает,
    # что «мой класс» идёт именно через users.school_class_id.
    school_class_id: Mapped[int | None] = mapped_column(ForeignKey("school_classes.id"))
    school_class: Mapped["SchoolClass | None"] = relationship(
        back_populates="students", foreign_keys=[school_class_id]
    )

    # Кейс (профильная группа) — ОДИН и у ученика, и у учителя
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"))
    case: Mapped["Case | None"] = relationship(back_populates="members")

    children: Mapped[list["User"]] = relationship(
        secondary=parent_children,
        primaryjoin=lambda: User.id == parent_children.c.parent_id,
        secondaryjoin=lambda: User.id == parent_children.c.child_id,
        back_populates="parents",
    )

    # Зеркально children: primaryjoin/secondaryjoin меняются местами
    # («найди строки, где child_id == мой id, возьми их parent_id»).
    parents: Mapped[list["User"]] = relationship(
        secondary=parent_children,
        primaryjoin=lambda: User.id == parent_children.c.child_id,
        secondaryjoin=lambda: User.id == parent_children.c.parent_id,
        back_populates="children",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"
