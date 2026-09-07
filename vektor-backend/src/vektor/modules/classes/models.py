from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vektor.core.database import Base

if TYPE_CHECKING:
    from vektor.modules.users.models import User


class TeacherClass(Base):
    """Связь «учитель ↔ класс» с атрибутами — association object, а не голая
    Table: у связи появились собственные данные (Этап 7m).

    subject — предметная роль ИМЕННО в этом классе («литература»), свободный
    текст: один учитель может вести литературу в 8-1 и русский в 5-2, поэтому
    предмет живёт на связке, а не на User. None — предмет не указан.

    is_homeroom — классный руководитель. Их может быть несколько на класс, и
    отдельной таблицы под них нет намеренно: кл. рук — это учитель класса с
    флагом, поэтому «руководитель, не числящийся среди учителей» невозможен
    физически, а не по договорённости с сервисом (до Этапа 7m это
    гарантировал только код `assign_homeroom`).
    """

    __tablename__ = "teacher_classes"

    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("school_classes.id"), primary_key=True)

    subject: Mapped[str | None] = mapped_column(String(100))
    is_homeroom: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    teacher: Mapped["User"] = relationship(foreign_keys=[teacher_id])
    school_class: Mapped["SchoolClass"] = relationship(back_populates="teacher_links")

    def __repr__(self) -> str:
        return f"<TeacherClass teacher={self.teacher_id} class={self.class_id}>"


class SchoolClass(Base):
    __tablename__ = "school_classes"

    __table_args__ = (
        UniqueConstraint("grade", "section", name="uq_school_classes_grade_section"),
        CheckConstraint("grade BETWEEN 1 AND 11", name="grade_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    grade: Mapped[int]
    section: Mapped[str] = mapped_column(String(10))

    students: Mapped[list["User"]] = relationship(
        back_populates="school_class", foreign_keys="User.school_class_id"
    )

    # Единственная ПИШУЩАЯ сторона связи с учителями: subject/is_homeroom
    # правятся здесь. delete-orphan — снятие учителя с класса удаляет строку.
    teacher_links: Mapped[list["TeacherClass"]] = relationship(
        back_populates="school_class", cascade="all, delete-orphan"
    )

    # Читающие проекции той же таблицы (viewonly — иначе SQLAlchemy справедливо
    # ругается на два пути записи в teacher_classes). `teachers` оставлен как
    # был: его читают права доступа в results/assessments, и переписывать их
    # ради этого среза незачем.
    teachers: Mapped[list["User"]] = relationship(secondary="teacher_classes", viewonly=True)
    homeroom_teachers: Mapped[list["User"]] = relationship(
        secondary="teacher_classes",
        # Строками, а не lambda: User здесь импортирован только под
        # TYPE_CHECKING (циклический импорт), а строку SQLAlchemy разрешает
        # по своему registry уже после конфигурации всех мапперов.
        primaryjoin="and_(SchoolClass.id == TeacherClass.class_id, "
        "TeacherClass.is_homeroom == True)",
        secondaryjoin="User.id == TeacherClass.teacher_id",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<SchoolClass id={self.id} grade={self.grade} section={self.section}>"


class PromotionRun(Base):
    """Один запуск ежегодного перевода всей школы на класс вперёд.

    Служит двум целям:
      - маркер «за этот учебный год перевод уже сделан» — партиальный
        уникальный индекс по academic_year среди строк с undone_at IS NULL
        не даёт запустить второй активный перевод за тот же год (повторный
        клик по кнопке — 409, а не второй сдвиг всей школы на класс вперёд);
      - аудит + возможность отката: snapshot хранит состояние КАЖДОГО
        затронутого ученика ДО перевода (класс и активность), поэтому undo
        восстанавливает состав точно, не «угадывая» его из текущего.

    Прошлую диагностику перевод не трогает — она держится на снапшотах
    Assessment.subject_class_id/subject_case_id/rater_role, а тут мы двигаем
    только текущее членство. См. classes/promotion.py.
    """

    __tablename__ = "promotion_runs"

    __table_args__ = (
        Index(
            "uq_promotion_runs_active_year",
            "academic_year",
            unique=True,
            postgresql_where=text("undone_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # Ярлык учебного года из shared.academic_year.academic_year_label
    # («2026/2027 учебный год»).
    academic_year: Mapped[str] = mapped_column(String(50))

    ran_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ran_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # Счётчики для экрана-résumé: moved / graduated / classes_created.
    summary: Mapped[dict] = mapped_column(JSON)

    # [{ "user_id", "old_class_id" | null, "was_active" }] — before-state под undo.
    snapshot: Mapped[list] = mapped_column(JSON)

    undone_at: Mapped[datetime | None] = mapped_column(DateTime)

    def __repr__(self) -> str:
        return f"<PromotionRun id={self.id} year={self.academic_year!r} undone={self.undone_at}>"
