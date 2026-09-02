# Модели Этапа 4 — анкеты 360.
#
# Три таблицы, цепочка респондент → субъект → вопрос → ответ:
#   Campaign   — «раунд» оценки («360 · июнь 2026»), даты, статус.
#   Assessment — одна анкета: респондент оценивает субъекта в рамках кампании.
#   Answer     — один ответ на один вопрос внутри анкеты (шкала 1–5).
#
# ВАЖНЫЙ УРОК из Этапа 3.6, который здесь повторяется в удвоенном виде:
# у Assessment ДВА FK в одну и ту же таблицу users (respondent_id и subject_id).
# SQLAlchemy не угадает, какой relationship по какому FK идёт — на каждом
# relationship к User обязателен явный foreign_keys=[...]. Точно как было с
# homeroom_teacher_id vs school_class_id.

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vektor.core.database import Base

from vektor.modules.cases.models import Case  # noqa: F401
from vektor.shared.enums import AssessmentStatus, CampaignStatus, RaterRole

if TYPE_CHECKING:
    from vektor.modules.classes.models import SchoolClass
    from vektor.modules.competencies.models import Question, QuestionnaireVersion
    from vektor.modules.users.models import User


# Паттерн хранения enum как строкового значения — копия User.role из
# users/models.py. Держим одинаково по всему проекту.
def _enum_col(enum_cls):
    return Enum(
        enum_cls,
        native_enum=False,
        length=20,
        values_callable=lambda e: [m.value for m in e],
    )


class Campaign(Base):
    """Кампания оценки — один раунд 360 (например «360 · июнь 2026»).

    Задаёт период сбора (год + месяц) и статус жизненного цикла
    (draft → active → closed). Все анкеты раунда ссылаются на неё через
    Assessment.campaign_id. Таблица в БД: `campaigns`.

    Окна приёма ответов (opens_at / closes_at) у кампании НЕТ: они были
    декоративными — ни одна проверка в бэкенде на них не смотрела, приём
    ответов режется только статусом, а во всех боевых данных обе колонки
    стояли в NULL. Удалены миграцией e7b3f9c2a815.
    """

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)

    title: Mapped[str] = mapped_column(String(255))

    # Период — ГОД + МЕСЯЦ числами, а не свободный ярлык строкой. Раньше это
    # был String(20) («2026» или «2026-06», формат не зафиксирован), и сравнение
    # периодов приходилось делать разбором регуляркой в Python: "2026" —
    # префикс "2026-02" и потому лексикографически МЕНЬШЕ, хотя по смыслу не
    # раньше. На проде это уже приводило к тому, что «последней» кампанией
    # класса выбиралась кампания-артефакт. С двумя числами хронологический
    # порядок снова выражается обычным ORDER BY.
    period_year: Mapped[int]

    period_month: Mapped[int]

    status: Mapped[CampaignStatus] = mapped_column(
        _enum_col(CampaignStatus), default=CampaignStatus.DRAFT
    )

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Редакция анкеты, по которой идёт кампания. Фиксируется при создании и
    # определяет набор вопросов: новая кампания получает действующую редакцию,
    # импортированная — архивную. Третий снапшот в этой таблице после
    # rater_role и subject_class_id, по той же причине — прошлое неизменно.
    questionnaire_version_id: Mapped[int] = mapped_column(ForeignKey("questionnaire_versions.id"))
    questionnaire_version: Mapped["QuestionnaireVersion"] = relationship()

    assessments: Mapped[list["Assessment"]] = relationship(back_populates="campaign")

    def __repr__(self) -> str:
        return f"<Campaign id={self.id} period={self.period_year}-{self.period_month:02d}>"


class Assessment(Base):
    """Одна анкета: респондент оценивает субъекта в рамках кампании.

    Самооценка — это просто respondent_id == subject_id (отдельного флага нет).
    Уникальна по тройке (кампания, респондент, субъект): один респондент
    оценивает одного субъекта в кампании ровно один раз. Собственно ответы
    лежат в Answer и удаляются вместе с анкетой (cascade). Таблица: `assessments`.

    rater_role фиксируется В МОМЕНТ ГЕНЕРАЦИИ и больше не пересчитывается.
    Это принципиально: состав класса и привязка родителей меняются (перевод
    в следующий класс — штатное событие каждый год), а результаты прошлой
    кампании обязаны остаться теми же. Если выводить роль при чтении из
    ТЕКУЩИХ связей, учитель прошлого года после перевода ученика молча
    станет «одноклассником»: его оценка исчезнет из слоя teacher и попадёт
    в пул анонимности peer. Роль уже известна в build_pairs — здесь мы её
    просто не выбрасываем.
    """

    __tablename__ = "assessments"

    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "respondent_id",
            "subject_id",
            name="uq_assessment_campaign_respondent_subject",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    status: Mapped[AssessmentStatus] = mapped_column(
        _enum_col(AssessmentStatus), default=AssessmentStatus.NOT_STARTED
    )

    rater_role: Mapped[RaterRole] = mapped_column(_enum_col(RaterRole))

    answers: Mapped[list["Answer"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )

    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"))
    campaign: Mapped["Campaign"] = relationship(back_populates="assessments")

    respondent_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    respondent: Mapped["User"] = relationship(foreign_keys=[respondent_id])

    subject_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    subject: Mapped["User"] = relationship(foreign_keys=[subject_id])

    # Класс субъекта НА МОМЕНТ ГЕНЕРАЦИИ — по той же причине, что и rater_role
    # выше: перевод ученика в следующий класс не должен переписывать прошлое.
    # Здесь это влияет на видимость условных вопросов (они только для 9–11):
    # если читать класс из User.school_class, то после перевода из 8-го в 9-й
    # в прошлогодней анкете задним числом «появились» бы три вопроса, на
    # которые никто не отвечал, и она перестала бы быть completed.
    # Nullable: у субъекта может не быть класса (учитель в пилотной кампании,
    # ученик вне класса) — тогда условные вопросы просто скрыты.
    subject_class_id: Mapped[int | None] = mapped_column(ForeignKey("school_classes.id"))
    subject_class: Mapped["SchoolClass | None"] = relationship()

    # Кейс субъекта НА МОМЕНТ ГЕНЕРАЦИИ — третий снапшот в этой таблице, по
    # той же причине, что класс выше: кейс у ученика один, но меняется, и
    # переход в другой кружок не должен переносить туда прошлую диагностику.
    # На видимость вопросов кейс НЕ влияет (возрастные границы живут на
    # классе) — он нужен для покрытия и разбора «по какому основанию выдана
    # эта анкета». Nullable: у анкеты, выданной по классу, кейса нет.
    subject_case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"))
    subject_case: Mapped["Case | None"] = relationship()

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<Assessment id={self.id} respondent={self.respondent_id} subject={self.subject_id}>"
        )


class Answer(Base):
    """Один ответ на один вопрос внутри анкеты по шкале 1–5.

    Уникален по паре (анкета, вопрос) — повторно ответить на тот же вопрос
    нельзя. Значение ограничено диапазоном 1..5 CheckConstraint'ом на уровне БД,
    поверх валидации Pydantic. Вопрос — это справочная запись (Question из
    competencies), при удалении анкеты он не трогается. Таблица: `answers`.
    """

    __tablename__ = "answers"

    __table_args__ = (
        UniqueConstraint("assessment_id", "question_id", name="uq_answer_assessment_question"),
        CheckConstraint("value BETWEEN 1 AND 5", name="answer_value_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    value: Mapped[int]

    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"))
    assessment: Mapped["Assessment"] = relationship(back_populates="answers")

    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    question: Mapped["Question"] = relationship()

    def __repr__(self) -> str:
        return f"<Answer id={self.id} question={self.question_id} value={self.value}>"
