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


class QuestionnaireVersionStatus(StrEnum):
    """Черновик анкеты редактируется свободно; после публикации — навсегда
    заморожен (см. QuestionnaireVersion.status в competencies/models.py)."""

    DRAFT = "draft"
    PUBLISHED = "published"


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


class AssessmentBasis(StrEnum):
    """По какому основанию выдана анкета — класс или кейс.

    Нужен потому, что у анкеты стоят ОБА снапшота сразу: subject_class_id
    проставляется всегда (от него зависит видимость возрастных вопросов), в
    том числе у анкеты, выданной за кружок. По снапшотам одним «кейс важнее
    класса» основание не восстанавливается: у ученика, попавшего в кампанию и
    классом, и кейсом, пары сливаются в ОДНУ анкету (merge_pairs), и тогда его
    самооценка, родители и учителя класса уезжали в строку кейса, а из класса
    ученик пропадал вовсе.

    Пишется при генерации и больше не пересчитывается — как rater_role.
    Класс приоритетнее кейса: если пара порождена обоими основаниями (учитель
    класса, он же руководитель кружка), анкета остаётся в основном потоке.
    """

    CLASS = "class"
    CASE = "case"
