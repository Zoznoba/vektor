from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.database import get_db
from vektor.modules.auth.dependencies import get_current_user, require_role
from vektor.modules.results import service
from vektor.modules.results.schemas import (
    CampaignCoverageOut,
    CaseResultsOut,
    ClassCampaignOut,
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
    "не по ответам), сравнение со школой за тот же период и метрики под "
    "радаром. campaign_id ОБЯЗАТЕЛЕН: строки классов школа переиспользует из "
    "года в год, поэтому «класс» без периода не определяет группу людей. "
    "Список периодов — /results/class/{class_id}/campaigns, он же включает "
    "архив прошлых наборов этой строки класса. В состав входят и те, кому "
    "анкеты выданы по этой строке (включая выбывших), и нынешние ученики, "
    "участвовавшие в этой кампании под прежним ярлыком. Доступно админу и "
    "учителю класса.",
)
async def get_class_results(
    class_id: int,
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ClassResultsOut:
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
    # Условие «кампания нынешней когорты», как у класса, кейсу намеренно НЕ
    # переносится: строки классов школа переиспользует под новый набор каждый
    # год целиком, а кружок живёт дальше со своим именем и меняет состав
    # постепенно. Подмены когорты, от которой защищаемся у класса, тут не
    # происходит, а фильтр отрезал бы доступ к архиву кружка — переключателя
    # периодов на экранах кейса пока нет.
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
    "баллы без дельт. campaign_id обязателен, состав — как у профиля класса. "
    "Доступно админу и учителю этого класса.",
)
async def get_class_dynamics(
    class_id: int,
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GroupDynamicsOut:
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
    "/class/{class_id}/campaigns",
    response_model=list[ClassCampaignOut],
    summary="Периоды диагностики класса",
    description="Кампании под переключатель на экране класса, свежие сверху: "
    "и выданные по этой строке класса (включая архив прошлых когорт), и те, "
    "где участвовали нынешние ученики под прежним ярлыком класса. Любого "
    "статуса, включая идущую. Доступно админу и учителю этого класса.",
)
async def list_class_campaigns(
    class_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ClassCampaignOut]:
    return await service.list_class_campaigns(db, class_id, user)


@router.get(
    "/class/{class_id}/roster",
    response_model=ClassRosterOut,
    summary="Состав класса с прогрессом диагностики",
    description="Строка на ученика: статус самооценки, сколько анкет про него "
    "завершено, итоговый балл и динамика к прошлому периоду; плюс метрики "
    "шапки экрана. Это экран хода диагностики, поэтому без campaign_id "
    "берётся последняя кампания ЛЮБОГО статуса, включая идущую, — но только "
    "среди тех, где участвовал кто-то из нынешних учеников класса. "
    "Доступно админу и учителю этого класса.",
)
async def get_class_roster(
    class_id: int,
    campaign_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ClassRosterOut:
    # Резолюция кампании живёт в сервисе, а не здесь: чтобы выбрать «последнюю
    # кампанию ЭТОЙ когорты», нужен состав класса, который сервис и так грузит
    # ради проверки прав. Заодно право проверяется ДО того, как ответ начнёт
    # зависеть от наличия кампаний.
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
