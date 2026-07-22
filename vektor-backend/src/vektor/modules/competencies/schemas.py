from pydantic import BaseModel, ConfigDict


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    text: str
    is_conditional: bool
    order: int


class CompetencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    description: str | None
    order: int
    questions: list[QuestionOut]
