from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vektor.core.database import Base

if TYPE_CHECKING:
    from vektor.modules.users.models import User

teacher_classes = Table(
    "teacher_classes",
    Base.metadata,
    Column("teacher_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("class_id", Integer, ForeignKey("school_classes.id"), primary_key=True),
)


class SchoolClass(Base):
    __tablename__ = "school_classes"

    __table_args__ = (
        UniqueConstraint("grade", "section", name="uq_school_classes_grade_section"),
        CheckConstraint("grade BETWEEN 1 AND 11", name="grade_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    grade: Mapped[int]
    section: Mapped[str] = mapped_column(String(10))

    # Классный руководитель — один из учителей класса (сервис гарантирует,
    # что при назначении он попадает и в teachers). foreign_keys явно: между
    # users и school_classes два FK-пути (см. комментарий в users/models.py).
    homeroom_teacher_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    homeroom_teacher: Mapped["User | None"] = relationship(foreign_keys=[homeroom_teacher_id])

    students: Mapped[list["User"]] = relationship(
        back_populates="school_class", foreign_keys="User.school_class_id"
    )
    teachers: Mapped[list["User"]] = relationship(secondary=teacher_classes)

    def __repr__(self) -> str:
        return f"<SchoolClass id={self.id} grade={self.grade} section={self.section}>"
