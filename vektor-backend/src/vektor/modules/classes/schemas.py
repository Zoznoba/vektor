from pydantic import BaseModel, ConfigDict
from vektor.modules.users.models import User

class SchoolClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    grade: int
    section: str
    students: list[User]
    teachers: list[User]