from enum import StrEnum


class UserRole(StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    PARENT = "parent"
    ADMIN = "admin"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"


class AssessmentStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class RaterRole(StrEnum):
    """Кем респондент приходится субъекту — роль оценивающего в агрегации
    результатов (Этап 5). Соответствует ролям в build_pairs
    (assessments/service.py): self / teacher / parent всегда, peer — только
    при include_peers."""

    SELF = "self"
    PEER = "peer"
    TEACHER = "teacher"
    PARENT = "parent"
