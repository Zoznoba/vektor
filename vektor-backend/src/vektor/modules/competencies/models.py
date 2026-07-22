# Справочник: 8 компетенций «Образа результата» + вопросы к ним.
#
# Это чисто справочные таблицы — их наполняют один раз (сидинг, см. миграцию),
# и почти никогда не меняют из приложения. Поэтому у Competency/Question
# НЕТ repository/service со сложной логикой: читать будем прямо через ORM.
#
# Question ссылается на Competency через ForeignKey — классическая связь
# «один ко многим» (одна компетенция — много вопросов).

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vektor.core.database import Base


class Competency(Base):
    __tablename__ = "competencies"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None]
    order: Mapped[int]
    questions: Mapped[list["Question"]] = relationship(back_populates="competency")

    def __repr__(self) -> str:
        return f"<Competency id={self.id} code={self.code}>"


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    competency_id: Mapped[int] = mapped_column(ForeignKey("competencies.id"))
    text: Mapped[str] = mapped_column(String(500))
    is_conditional: Mapped[bool] = mapped_column(default=False)
    order: Mapped[int]
    competency: Mapped["Competency"] = relationship(back_populates="questions")

    def __repr__(self) -> str:
        return f"<Question id={self.id} competency_id={self.competency_id}>"
