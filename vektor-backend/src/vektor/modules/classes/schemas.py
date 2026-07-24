from pydantic import BaseModel, ConfigDict, Field

from vektor.modules.auth.schemas import UserOut


class SchoolClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    grade: int
    section: str
    students: list[UserOut]
    teachers: list[UserOut]


class SchoolClassCreate(BaseModel):
    grade: int = Field(ge=1, le=11)
    section: str = Field(min_length=1, max_length=10)


class AssignStudentsIn(BaseModel):
    student_ids: list[int]


class AssignTeachersIn(BaseModel):
    teacher_ids: list[int]
