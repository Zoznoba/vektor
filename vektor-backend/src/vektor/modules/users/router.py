# HTTP-слой users: «кто я», админский список, связь родитель—ребёнок.

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vektor.core.config import settings
from vektor.core.database import get_db
from vektor.modules.auth.dependencies import get_current_user, require_role
from vektor.modules.auth.schemas import UserOut
from vektor.modules.cases.models import Case
from vektor.modules.classes.models import SchoolClass
from vektor.modules.users import service
from vektor.modules.users.models import User
from vektor.modules.users.schemas import (
    AssignChildrenIn,
    BulkCreateIn,
    BulkCreateOut,
    MeOut,
    ParentWithChildrenOut,
    ResetPasswordOut,
    SetUserActiveIn,
)
from vektor.shared.academic_year import academic_year_label
from vektor.shared.class_label import class_label
from vektor.shared.enums import UserRole

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=MeOut,
    summary="Текущий пользователь",
    description="Профиль пользователя по токену авторизации, плюс класс, кейс "
    "и учебный год для шапки дашборда.",
)
async def read_me(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MeOut:
    # Класс нужен дашборду в шапке («8-1 класс»). Отдельным запросом, а не
    # relationship на UserOut: UserOut уходит ещё в списки и вложенные схемы,
    # где класс не нужен, а ленивая подгрузка там дала бы MissingGreenlet.
    school_class = None
    if user.school_class_id is not None:
        school_class = await db.get(SchoolClass, user.school_class_id)
    # Кейс — тем же приёмом и по той же причине, что класс выше.
    kase = None
    if user.case_id is not None:
        kase = await db.get(Case, user.case_id)
    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        class_label=class_label(school_class.grade, school_class.section) if school_class else None,
        case_name=kase.name if kase else None,
        academic_year=academic_year_label(date.today()),
    )


@router.get(
    "",
    response_model=list[UserOut],
    summary="Список пользователей",
    description="Пользователи школы с опциональными фильтрами по роли, "
    "подстроке в имени/email, классу (только для учеников) и кейсу. "
    "`without_case=true` отбирает тех, кто не состоит ни в одном кейсе, — "
    "именно они могут быть кандидатами на привязку (членство в кейсе одно). "
    "Только админ.",
)
async def get_all_users(
    role: UserRole | None = Query(None),
    search: str | None = Query(None, min_length=1),
    class_id: int | None = Query(None),
    case_id: int | None = Query(None),
    without_case: bool = Query(False),
    _admin_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).order_by(User.id)
    if role is not None:
        query = query.where(User.role == role)
    if search is not None:
        pattern = f"%{search.strip()}%"
        query = query.where(
            func.lower(User.full_name).like(func.lower(pattern))
            | func.lower(User.email).like(func.lower(pattern))
        )
    if class_id is not None:
        query = query.where(User.school_class_id == class_id)
    if case_id is not None:
        query = query.where(User.case_id == case_id)
    # Отдельный флаг, а не case_id=null: «не фильтровать по кейсу» и «взять
    # только бескейсовых» — разные запросы, а через один параметр их не
    # различить (отсутствие query-параметра и null неотличимы в HTTP).
    if without_case:
        query = query.where(User.case_id.is_(None))
    all_users = (await db.execute(query)).scalars().all()
    return all_users


@router.patch(
    "/{user_id}/active",
    response_model=UserOut,
    summary="Активировать/деактивировать пользователя",
    description="Единственная форма «удаления» пользователя в системе: "
    "деактивация мгновенно блокирует вход и все авторизованные запросы, но "
    "сохраняет историю (ответы анкет, привязки к классу/детям) нетронутой. "
    "Обратимо в любой момент. Нельзя деактивировать самого себя. Только "
    "админ.",
)
async def update_user_active_status(
    user_id: int,
    data: SetUserActiveIn,
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_role(UserRole.ADMIN)),
) -> User:
    return await service.set_user_active(db, user_id, data.is_active, admin_user)


@router.post(
    "/{user_id}/reset-password",
    response_model=ResetPasswordOut,
    summary="Сбросить пароль пользователя",
    description="Сгенерировать новый временный пароль и показать его один "
    "раз в ответе — почтовой рассылки в системе пока нет (см. "
    "BulkCreateOut.default_password), другого способа узнать пароль не "
    "будет. Только админ.",
)
async def reset_user_password(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin_user: User = Depends(require_role(UserRole.ADMIN)),
) -> ResetPasswordOut:
    new_password = await service.reset_password(db, user_id)
    return ResetPasswordOut(new_password=new_password)


@router.post(
    "/bulk",
    response_model=BulkCreateOut,
    status_code=status.HTTP_201_CREATED,
    summary="Массовая загрузка пользователей",
    description="Завести пачку пользователей одним вызовом; опциональный "
    "`class_id` разом привязывает всех `role=student` к классу, `case_id` — "
    "всех учеников и учителей к кейсу. Атомарно — "
    "любая ошибка (дубль внутри пачки, занятый email, нет класса) откатывает "
    "всю пачку. ВРЕМЕННО: всем ставится общий пароль из настроек, он же "
    "возвращается в ответе. Только админ.",
)
async def bulk_create_users(
    data: BulkCreateIn,
    db: AsyncSession = Depends(get_db),
    _admin_user: User = Depends(require_role(UserRole.ADMIN)),
) -> BulkCreateOut:
    created = await service.bulk_create_users(db, data.users, data.class_id, data.case_id)

    return BulkCreateOut(
        created=created,
        class_id=data.class_id,
        case_id=data.case_id,
        default_password=settings.bulk_default_password,
    )


@router.get(
    "/{user_id}/children",
    response_model=list[UserOut],
    summary="Дети родителя",
    description="Список детей, привязанных к пользователю с ролью PARENT. "
    "Админ — про любого родителя; сам родитель — только про себя.",
)
async def get_children(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[UserOut]:
    is_self_parent = current_user.id == user_id and current_user.role == UserRole.PARENT
    if current_user.role != UserRole.ADMIN and not is_self_parent:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    parent = await service.get_parent_with_children(db, user_id)
    return parent.children


@router.post(
    "/{user_id}/children",
    response_model=ParentWithChildrenOut,
    summary="Привязать детей к родителю",
    description="Массово и идемпотентно привязать учеников к родителю "
    "(повторная привязка — no-op). Цель — только PARENT, дети — только "
    "STUDENT, иначе 409. Только админ.",
)
async def assign_children_to_parent(
    user_id: int,
    data: AssignChildrenIn,
    db: AsyncSession = Depends(get_db),
    _admin_user: User = Depends(require_role(UserRole.ADMIN)),
) -> ParentWithChildrenOut:
    return await service.assign_children(db, user_id, data.child_ids)
