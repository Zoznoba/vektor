# Справочник: 11 критериев «Образа результата» + вопросы к ним.
#
# Это чисто справочные таблицы — их наполняют один раз (сидинг, см. миграцию),
# и почти никогда не меняют из приложения. Поэтому у Competency/Question
# НЕТ repository/service со сложной логикой: читать будем прямо через ORM.
#
# Question ссылается на Competency через ForeignKey — классическая связь
# «один ко многим» (одна компетенция — много вопросов).

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vektor.core.database import Base
from vektor.shared.enums import QuestionnaireVersionStatus


class QuestionnaireVersion(Base):
    """Редакция анкеты: с каким набором вопросов работает кампания.

    Появилась под импорт истории — старый замер собран по ДРУГОЙ ревизии
    инструмента (то же 8 компетенций, но другое число вопросов внутри них),
    и привязать его ответы к текущим вопросам физически нельзя. Заодно
    закрывает требование прототипа: публикация новых формулировок создаёт
    версию, а не переписывает старую, и на графике динамики линия рвётся на
    стыке — текст оговорки лежит в note.

    is_current — редакция, которую получают НОВЫЕ кампании. Ровно одна:
    гарантирует частичный уникальный индекс uq_questionnaire_versions_current.

    status — жизненный цикл конструктора анкеты (Этап 7): draft редактируется
    свободно (OutcomeArea/Competency/Question можно добавлять, менять,
    архивировать), published заморожен навсегда. Публикация — один раз и
    необратимо: назад в draft редакция не возвращается.
    """

    __tablename__ = "questionnaire_versions"

    # Частичный уникальный индекс: is_current=false может повторяться сколько
    # угодно, true — ровно один раз. Дублирует миграцию c3f81ad0e7b5 намеренно,
    # чтобы схема из моделей (её строит create_all в тестах) не расходилась с
    # той, что даёт Alembic.
    __table_args__ = (
        Index(
            "uq_questionnaire_versions_current",
            "is_current",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    # Оговорка для стыка версий; None — «сравнение корректно».
    note: Mapped[str | None] = mapped_column(String(500))
    is_current: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(20), default=QuestionnaireVersionStatus.PUBLISHED)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    questions: Mapped[list["Question"]] = relationship(back_populates="version")

    def __repr__(self) -> str:
        return f"<QuestionnaireVersion id={self.id} code={self.code!r}>"


class OutcomeArea(Base):
    """«ОР / навык» — верхний уровень методики: 6 областей «Образа результата».

    Группирует критерии. Профессиональное самоопределение школа разбивает на
    ДВЕ области по возрасту — «(5-11)» и «(9-11)»; именно так в методике и
    закодирована возрастная условность.
    """

    __tablename__ = "outcome_areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    order: Mapped[int]

    # Не версионируются (см. Competency.is_archived ниже) — общий список на
    # все редакции. is_archived скрывает область из НОВЫХ черновиков, не
    # трогая прошлые кампании. is_draft — область добавлена в ещё не
    # опубликованный черновик: при публикации становится false (см.
    # service.publish_version), при отмене черновика строка удаляется целиком.
    is_archived: Mapped[bool] = mapped_column(default=False)
    is_draft: Mapped[bool] = mapped_column(default=False)

    competencies: Mapped[list["Competency"]] = relationship(back_populates="outcome_area")

    def __repr__(self) -> str:
        return f"<OutcomeArea id={self.id} code={self.code}>"


class Competency(Base):
    """Критерий методики — то, что реально считается и показывается в разрезе.

    Ровно 3 вопроса на критерий, 11 критериев. Название сохранено историческое
    («компетенция»), потому что на него завязан весь модуль results.
    """

    __tablename__ = "competencies"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None]
    order: Mapped[int]
    questions: Mapped[list["Question"]] = relationship(back_populates="competency")

    outcome_area_id: Mapped[int] = mapped_column(ForeignKey("outcome_areas.id"))
    outcome_area: Mapped["OutcomeArea"] = relationship(back_populates="competencies")

    # Возрастные границы критерия; None — без ограничения. Пришли на смену
    # Question.is_conditional: условность — свойство КРИТЕРИЯ, а не вопроса.
    # Иначе критерий считался бы по неполному набору вопросов, и средний балл
    # прыгал бы при переходе из класса в класс сам по себе.
    min_grade: Mapped[int | None]
    max_grade: Mapped[int | None]

    # См. OutcomeArea.is_archived/is_draft — тот же смысл, критерий тоже общий
    # на все редакции анкеты, а не принадлежит одной версии.
    is_archived: Mapped[bool] = mapped_column(default=False)
    is_draft: Mapped[bool] = mapped_column(default=False)

    def __repr__(self) -> str:
        return f"<Competency id={self.id} code={self.code}>"


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    competency_id: Mapped[int] = mapped_column(ForeignKey("competencies.id"))
    text: Mapped[str] = mapped_column(String(500))
    # Позиция внутри критерия: 0, 1 или 2.
    order: Mapped[int]
    competency: Mapped["Competency"] = relationship(back_populates="questions")

    # Вопрос принадлежит РЕДАКЦИИ анкеты. Без фильтра по ней выборка вопросов
    # склеила бы все редакции разом — см. get_visible_questions_for_assessment.
    version_id: Mapped[int] = mapped_column(ForeignKey("questionnaire_versions.id"))
    version: Mapped["QuestionnaireVersion"] = relationship(back_populates="questions")

    def __repr__(self) -> str:
        return f"<Question id={self.id} competency_id={self.competency_id}>"
