# Pydantic-схемы assessments. Вход — что админ имеет право прислать,
# выход — что мы готовы показать. Ответы (Answer) появятся в срезе 4c.

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from vektor.shared.enums import CampaignStatus


class CampaignCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    period: str = Field(min_length=1, max_length=20)
    opens_at: datetime | None = None
    closes_at: datetime | None = None


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    period: str
    status: CampaignStatus
    opens_at: datetime | None
    closes_at: datetime | None
    created_at: datetime


class GenerateIn(BaseModel):
    class_ids: list[int] = Field(min_length=1)
    # Оценивают ли одноклассники друг друга. По умолчанию нет — только
    # самооценка + учителя + родители. True добавляет пиров (student→classmate).
    include_peers: bool = False


class GenerateResult(BaseModel):
    created: int
    campaign: CampaignOut
