from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.modules.auth.dependencies import get_current_user, require_role
from vektor.modules.results import service
from vektor.modules.results.schemas import (
    CampaignCoverageOut,
    CaseResultsOut,
    ClassResultsOut,
    ClassRosterOut,
    DynamicsOut,
    GroupDynamicsOut,
    ResultsOut,
    SubjectCampaignOut,
)
from vektor.modules.users.models import User
from vektor.shared.enums import UserRole

router = APIRouter(prefix="/results", tags=["results"])

# ВНИМАНИЕ на порядок маршрутов: пути с литеральным первым сегментом
# (/class/..., /campaigns/...) объявлены ДО /{subject_id}. FastAPI разбирает
# маршруты в порядке объявления, и хотя конкретно эти по числу сегментов с
# /{subject_id} не пересекаются, держим литералы выше — так добавление
# следующего /{subject_id}/... не превратит /class/5 в «субъект по имени class».


@router.get(
    "/class/{class_id}",
    response_model=ClassResultsOut,
    summary="Профиль класса",
    description="Средний профиль класса по критериям (среднее по ученикам, "
    "не по ответам), сравнение со школой за тот же период и зоны роста "
    "класса по охвату. Без campaign_id берётся последняя ЗАВЕРШЁННАЯ "
    "кампания класса; по незавершённой результаты не отдаются (409). "
    "Доступно админу и учителю этого класса.",
)
async def get_class_results(
    class_id: int,
    campaign_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ClassResultsOut:
    if campaign_id is None:
        campaign_id = await service.latest_campaign_id_for_class(db, class_id)
        if campaign_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="У класса пока нет результатов",
            )
    return await service.get_class_results(db, class_id, campaign_id, user)


@router.get(
    "/case/{case_id}",
    response_model=CaseResultsOut,
    summary="Профиль кейса",
    description="Средний профиль профильной группы по критериям (среднее по "
    "ученикам, не по ответам), сравнение со школой за тот же период и зоны "
    "роста группы по охвату. Без campaign_id берётся последняя ЗАВЕРШЁННАЯ "
    "кампания кейса. Доступно админу и руководителю этого кейса.",
)
async def get_case_results(
    case_id: int,
    campaign_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CaseResultsOut:
    if campaign_id is None:
        campaign_id = await service.latest_campaign_id_for_case(db, case_id)
        if campaign_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="У кейса пока нет результатов",
            )
    return await service.get_case_results(db, case_id, campaign_id, user)


@router.get(
    "/class/{class_id}/dynamics",
    response_model=GroupDynamicsOut,
    summary="Динамика класса по критериям",
    description="Средний профиль класса в текущем периоде против предыдущего, "
    "по критериям. Сравниваются одни и те же ученики (те, у кого есть оба "
    "периода), дельты — только по общему ядру критериев. Отсутствие "
    "предыдущего периода — не ошибка: `previous_campaign_id=null` и текущие "
    "баллы без дельт. Доступно админу и учителю этого класса.",
)
async def get_class_dynamics(
    class_id: int,
    campaign_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GroupDynamicsOut:
    if campaign_id is None:
        campaign_id = await service.latest_campaign_id_for_class(db, class_id)
        if campaign_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="У класса пока нет результатов",
            )
    return await service.get_class_dynamics(db, class_id, campaign_id, user)


@router.get(
    "/case/{case_id}/dynamics",
    response_model=GroupDynamicsOut,
    summary="Динамика кейса по критериям",
    description="То же, что динамика класса, но по профильной группе. "
    "Доступно админу и руководителю этого кейса.",
)
async def get_case_dynamics(
    case_id: int,
    campaign_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GroupDynamicsOut:
    if campaign_id is None:
        campaign_id = await service.latest_campaign_id_for_case(db, case_id)
        if campaign_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="У кейса пока нет результатов",
            )
    return await service.get_case_dynamics(db, case_id, campaign_id, user)


@router.get(
    "/class/{class_id}/roster",
    response_model=ClassRosterOut,
    summary="Состав класса с прогрессом диагностики",
    description="Строка на ученика: статус самооценки, сколько анкет про него "
    "завершено, итоговый балл и динамика к прошлому периоду; плюс метрики "
    "шапки экрана. Это экран хода диагностики, поэтому без campaign_id "
    "берётся последняя кампания ЛЮБОГО статуса, включая идущую. "
    "Доступно админу и учителю этого класса.",
)
async def get_class_roster(
    class_id: int,
    campaign_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ClassRosterOut:
    if campaign_id is None:
        # Экран мониторинга: берём последнюю кампанию ЛЮБОГО статуса, включая
        # идущую сейчас — иначе во время диагностики учитель видел бы прошлый
        # год вместо того, по кому анкеты ещё не заполнены. Балльные экраны
        # (профиль класса, результаты ученика) — наоборот, только завершённые.
        campaign_id = await service.latest_campaign_id_for_class(db, class_id, only_completed=False)
        if campaign_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="У класса пока нет результатов",
            )
    return await service.get_class_roster(db, class_id, campaign_id, user)


@router.get(
    "/campaigns/{campaign_id}/coverage",
    response_model=CampaignCoverageOut,
    summary="Покрытие кампании",
    description="«X из Y анкет» заполнено по каждому классу И кейсу кампании. "
    "Группировка — по основанию выдачи (снапшоты subject_case_id / "
    "subject_class_id на момент генерации): анкета попадает ровно в одну "
    "строку, поэтому сумма строк равна общему числу анкет. Плюс детализация "
    "по ученикам: статус самооценки, счётчики по родителям и учителям и "
    "поимённый состав каждого слоя со статусом анкеты. Только админ.",
)
async def get_campaign_coverage(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.ADMIN)),
) -> CampaignCoverageOut:
    # Покрытие по всей школе — админский экран кампании, поэтому роль жёстко
    # ADMIN, а не «учитель своего класса», как у профиля класса.
    return await service.get_campaign_coverage(db, campaign_id)


@router.get(
    "/{subject_id}",
    response_model=ResultsOut,
    summary="Результаты пользователя",
    description="Агрегация по критериям (self/peer/teacher/parent/others/overall), "
    "разрыв самооценки и зоны роста. Оценки одноклассников скрываются, пока "
    "по критерию не набралось 3 разных респондента-одноклассника. Без "
    "campaign_id берётся последняя ЗАВЕРШЁННАЯ кампания субъекта; по "
    "незавершённой кампании, переданной явным id, — 409. Доступно самому "
    "субъекту, админу, учителю и родителю.",
)
async def get_results(
    subject_id: int,
    campaign_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResultsOut:
    # campaign_id опционален: дашборд ученика показывает «мои результаты» и
    # про кампании не знает. Без него берём последнюю, где у субъекта есть
    # анкеты. Нет ни одной — 404, а не пустой ответ: «результатов ещё нет» и
    # «такого субъекта нет» фронт различает по detail.
    if campaign_id is None:
        campaign_id = await service.latest_campaign_id_for_subject(db, subject_id)
        if campaign_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="У пользователя пока нет результатов",
            )
    return await service.get_subject_results(db, subject_id, campaign_id, user)


@router.get(
    "/{subject_id}/campaigns",
    response_model=list[SubjectCampaignOut],
    summary="Кампании субъекта",
    description="Завершённые кампании, где у субъекта есть хотя бы одна "
    "анкета — для переключателя периода на странице результатов. Идущие и "
    "черновые кампании не показываются: результатов по ним ещё нет.",
)
async def list_subject_campaigns(
    subject_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SubjectCampaignOut]:
    return await service.list_subject_campaigns(db, subject_id, user)


@router.get(
    "/{subject_id}/dynamics",
    response_model=DynamicsOut,
    summary="Динамика по годам",
    description="Сравнение с предыдущей завершённой кампанией субъекта: "
    "дельты только по критериям, общим для обоих периодов (ядро). Нет "
    "предыдущего периода — не 404, а текущие баллы с "
    "`previous_campaign_id=None`.",
)
async def get_dynamics(
    subject_id: int,
    campaign_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DynamicsOut:
    if campaign_id is None:
        campaign_id = await service.latest_campaign_id_for_subject(db, subject_id)
        if campaign_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="У пользователя пока нет результатов",
            )
    return await service.get_subject_dynamics(db, subject_id, campaign_id, user)
