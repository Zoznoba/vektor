# Pydantic-схемы users, которых нет в auth: связь родитель—ребёнок.

from pydantic import BaseModel, ConfigDict

from vektor.modules.auth.schemas import UserOut


class AssignChildrenIn(BaseModel):
    child_ids: list[int]


class ParentWithChildrenOut(UserOut):
    """Родитель вместе со списком привязанных детей."""

    model_config = ConfigDict(from_attributes=True)

    children: list[UserOut]
