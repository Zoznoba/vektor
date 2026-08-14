# Юнит-тесты чистого доменного ядра build_pairs — матрица «кто кого оценивает»
# для одного класса. Без БД: гоняем на голых id.
#
# build_pairs возвращает dict {(respondent, subject): RaterRole} — роль нужна
# дальше, она сохраняется в Assessment.rater_role при генерации. Структурные
# проверки поэтому идут по .keys().
#
# generate_assessments (оркестрация с БД) покрывается отдельно интеграционными
# тестами — тут только доменные правила.

import pytest
from httpx import AsyncClient

from vektor.modules.assessments.service import build_pairs, merge_pairs
from vektor.shared.enums import RaterRole


def test_self_assessment_always_present() -> None:
    # Самооценка (s, s) есть у каждого ученика — даже без родителей/учителей/пиров.
    pairs = build_pairs(student_ids=[1, 2, 3], parent_ids_by_student={}, teacher_ids=[])
    assert pairs.keys() == {(1, 1), (2, 2), (3, 3)}
    assert all(role == RaterRole.SELF for role in pairs.values())


def test_parent_evaluates_only_own_child() -> None:
    # Родитель 10 привязан к ученику 1, родитель 20 — к ученику 2.
    # Родитель оценивает ТОЛЬКО своего ребёнка, не весь класс.
    pairs = build_pairs(
        student_ids=[1, 2],
        parent_ids_by_student={1: [10], 2: [20]},
        teacher_ids=[],
    )
    assert pairs[(10, 1)] == RaterRole.PARENT
    assert pairs[(20, 2)] == RaterRole.PARENT
    assert (10, 2) not in pairs  # чужому ребёнку — нет
    assert (20, 1) not in pairs


def test_teacher_evaluates_every_student() -> None:
    # Учитель класса оценивает каждого ученика.
    pairs = build_pairs(student_ids=[1, 2], parent_ids_by_student={}, teacher_ids=[100])
    assert pairs[(100, 1)] == RaterRole.TEACHER
    assert pairs[(100, 2)] == RaterRole.TEACHER


def test_no_peers_by_default() -> None:
    # include_peers=False (по умолчанию): одноклассники друг друга НЕ оценивают.
    # В парах не должно быть (ученик -> другой ученик).
    students = [1, 2, 3]
    pairs = build_pairs(student_ids=students, parent_ids_by_student={}, teacher_ids=[])
    peer_pairs = {(r, s) for r in students for s in students if r != s}
    assert pairs.keys() & peer_pairs == set()


def test_peers_added_and_symmetric_when_flag_on() -> None:
    # include_peers=True: каждый ученик оценивает каждого другого, симметрично.
    students = [1, 2, 3]
    pairs = build_pairs(
        student_ids=students, parent_ids_by_student={}, teacher_ids=[], include_peers=True
    )
    expected_peers = {(r, s) for r in students for s in students if r != s}
    assert expected_peers <= pairs.keys()
    # Симметрия: если есть (1, 2), есть и (2, 1).
    for r, s in expected_peers:
        assert (s, r) in pairs
        assert pairs[(r, s)] == RaterRole.PEER


def test_peers_flag_only_adds_peers_nothing_else_changes() -> None:
    # Разница между True и False — РОВНО множество пиров, ничего лишнего.
    students = [1, 2]
    base = build_pairs(students, {1: [10]}, [20], include_peers=False)
    with_peers = build_pairs(students, {1: [10]}, [20], include_peers=True)
    assert with_peers.keys() - base.keys() == {(1, 2), (2, 1)}


def test_student_without_parents_does_not_crash() -> None:
    # Ученик 2 не в словаре родителей — .get(s, []) страхует, пары родителя нет.
    pairs = build_pairs(student_ids=[1, 2], parent_ids_by_student={1: [10]}, teacher_ids=[])
    assert (10, 1) in pairs
    # Единственная пара с субъектом 2 — его самооценка; чужих родителей ему не досталось.
    assert {(resp, subj) for resp, subj in pairs if subj == 2} == {(2, 2)}


def test_duplicate_collapses_by_key() -> None:
    # Один и тот же человек — и родитель ученика 1, и учитель класса (id=10).
    # Пара (10, 1) должна встретиться один раз, роль — более специфичная.
    pairs = build_pairs(student_ids=[1], parent_ids_by_student={1: [10]}, teacher_ids=[10])
    assert pairs.keys() == {(1, 1), (10, 1)}
    assert pairs[(10, 1)] == RaterRole.TEACHER


def test_role_priority_is_order_independent() -> None:
    # Роль при коллизии не должна зависеть от порядка циклов внутри build_pairs:
    # человек 10 и родитель, и учитель — teacher выигрывает в любом случае.
    as_parent_first = build_pairs([1], {1: [10]}, [10])
    as_teacher_only = build_pairs([1], {}, [10])
    assert as_parent_first[(10, 1)] == as_teacher_only[(10, 1)] == RaterRole.TEACHER


def test_self_wins_over_peer_for_same_student() -> None:
    # Самооценка не должна быть перетёрта пиром при include_peers.
    pairs = build_pairs([1, 2], {}, [], include_peers=True)
    assert pairs[(1, 1)] == RaterRole.SELF
    assert pairs[(2, 2)] == RaterRole.SELF


def test_empty_class_gives_empty_matrix() -> None:
    # Нет учеников — нет субъектов — пустая матрица (учителя без учеников не с кем).
    assert build_pairs(student_ids=[], parent_ids_by_student={}, teacher_ids=[42]) == {}


@pytest.mark.parametrize("include_peers", [False, True])
def test_full_scenario_exact_set(include_peers: bool) -> None:
    # Полный сценарий: 2 ученика, у ученика 1 родитель 10, учитель класса 20.
    base = {(1, 1), (2, 2), (10, 1), (20, 1), (20, 2)}
    expected = base | ({(1, 2), (2, 1)} if include_peers else set())
    pairs = build_pairs(
        student_ids=[1, 2],
        parent_ids_by_student={1: [10]},
        teacher_ids=[20],
        include_peers=include_peers,
    )
    assert pairs.keys() == expected


def test_merge_pairs_keeps_most_specific_role() -> None:
    # Человек 10 — учитель в одном классе кампании и родитель ученика в другом.
    # Слепой dict.update() дал бы роль, зависящую от порядка обхода классов.
    first = build_pairs([1], {}, [10])  # (10, 1) -> teacher
    second = build_pairs([1], {1: [10]}, [])  # (10, 1) -> parent

    merged_one_way: dict = {}
    merge_pairs(merged_one_way, first)
    merge_pairs(merged_one_way, second)

    merged_other_way: dict = {}
    merge_pairs(merged_other_way, second)
    merge_pairs(merged_other_way, first)

    assert merged_one_way[(10, 1)] == merged_other_way[(10, 1)] == RaterRole.TEACHER


# --- Интеграционные тесты эндпоинтов (оркестрация generate_assessments) ---
# Сценарий строится через реальный API: класс + 2 ученика + родитель + учитель.


async def _register(client: AsyncClient, email: str, role: str) -> int:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": f"Тест {role}", "role": role},
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
async def scenario(client: AsyncClient, admin_headers: dict[str, str]) -> dict:
    """Класс 10-A: ученики s1, s2; родитель p1 → ребёнок s1; учитель t1.

    Всё через API (как это делает админ в реальной панели). Матрица без пиров:
    self(s1,s2)=2 + parent(p1→s1)=1 + teacher(t1→s1,s2)=2 = 5 анкет.
    """
    s1 = await _register(client, "s1@vektor.ru", "student")
    s2 = await _register(client, "s2@vektor.ru", "student")
    p1 = await _register(client, "p1@vektor.ru", "parent")
    t1 = await _register(client, "t1@vektor.ru", "teacher")

    cls = (
        await client.post("/classes", json={"grade": 10, "section": "a"}, headers=admin_headers)
    ).json()
    class_id = cls["id"]
    await client.post(
        f"/classes/{class_id}/students", json={"student_ids": [s1, s2]}, headers=admin_headers
    )
    await client.post(
        f"/classes/{class_id}/teachers", json={"teacher_ids": [t1]}, headers=admin_headers
    )
    await client.post(f"/users/{p1}/children", json={"child_ids": [s1]}, headers=admin_headers)

    return {
        "class_id": class_id,
        "headers": admin_headers,
        "ids": {"s1": s1, "s2": s2, "p1": p1, "t1": t1},
    }


async def _create_campaign(client: AsyncClient, headers: dict[str, str]) -> int:
    response = await client.post(
        "/campaigns", json={"title": "360 · июнь 2026", "period": "2026-06"}, headers=headers
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_create_campaign_starts_as_draft(client: AsyncClient, admin_headers) -> None:
    response = await client.post(
        "/campaigns", json={"title": "360 · июнь 2026", "period": "2026-06"}, headers=admin_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["title"] == "360 · июнь 2026"


async def test_create_campaign_requires_admin(client: AsyncClient, register_user) -> None:
    login = await client.post("/auth/login", json=register_user)
    student_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = await client.post(
        "/campaigns", json={"title": "X", "period": "2026-06"}, headers=student_headers
    )
    assert response.status_code == 403


async def test_generate_default_no_peers(client: AsyncClient, scenario) -> None:
    cid = await _create_campaign(client, scenario["headers"])
    response = await client.post(
        f"/campaigns/{cid}/generate",
        json={"class_ids": [scenario["class_id"]]},
        headers=scenario["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    # 5 анкет (без пиров) и кампания стала active.
    assert body["created"] == 5
    assert body["campaign"]["status"] == "active"


async def test_generate_with_peers_adds_pairs(client: AsyncClient, scenario) -> None:
    cid = await _create_campaign(client, scenario["headers"])
    response = await client.post(
        f"/campaigns/{cid}/generate",
        json={"class_ids": [scenario["class_id"]], "include_peers": True},
        headers=scenario["headers"],
    )
    assert response.status_code == 200
    # 5 базовых + 2 пира (s1↔s2) = 7.
    assert response.json()["created"] == 7


async def test_generate_is_idempotent(client: AsyncClient, scenario) -> None:
    cid = await _create_campaign(client, scenario["headers"])
    payload = {"class_ids": [scenario["class_id"]]}
    first = await client.post(
        f"/campaigns/{cid}/generate", json=payload, headers=scenario["headers"]
    )
    second = await client.post(
        f"/campaigns/{cid}/generate", json=payload, headers=scenario["headers"]
    )
    assert first.json()["created"] == 5
    assert second.json()["created"] == 0  # повтор ничего не создаёт


async def test_generate_unknown_campaign_404(client: AsyncClient, admin_headers) -> None:
    response = await client.post(
        "/campaigns/99999/generate", json={"class_ids": [1]}, headers=admin_headers
    )
    assert response.status_code == 404


async def test_generate_requires_admin(client: AsyncClient, scenario, register_user) -> None:
    cid = await _create_campaign(client, scenario["headers"])
    login = await client.post("/auth/login", json=register_user)
    student_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = await client.post(
        f"/campaigns/{cid}/generate",
        json={"class_ids": [scenario["class_id"]]},
        headers=student_headers,
    )
    assert response.status_code == 403


# --- 4c-1: чтение анкеты (GET /assessments/{id}) ---
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from vektor.modules.assessments.models import Assessment, Campaign  # noqa: E402
from vektor.modules.assessments.service import is_question_visible  # noqa: E402
from vektor.modules.competencies.models import (  # noqa: E402
    Competency,
    OutcomeArea,
    Question,
    QuestionnaireVersion,
)


@pytest.mark.parametrize(
    ("min_grade", "max_grade", "grade", "expected"),
    [
        # Границ нет — критерий виден всегда, класс не важен.
        (None, None, 10, True),
        (None, None, 7, True),
        (None, None, None, True),
        # Профпробы: 9..11.
        (9, 11, 9, True),
        (9, 11, 10, True),
        (9, 11, 11, True),
        (9, 11, 8, False),
        (9, 11, 12, False),
        (9, 11, None, False),  # класс неизвестен — скрыт, без падения
        # Односторонние границы: «с 5 класса» и «по 4 класс».
        (5, None, 11, True),
        (5, None, 4, False),
        (None, 4, 3, True),
        (None, 4, 5, False),
    ],
)
def test_is_question_visible(
    min_grade: int | None, max_grade: int | None, grade: int | None, expected: bool
) -> None:
    assert is_question_visible(min_grade, max_grade, grade) is expected


@pytest.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


async def _current_version_id(db_session) -> int:
    """id действующей редакции анкеты (её сидит фикстура db_engine)."""
    row = await db_session.execute(
        select(QuestionnaireVersion.id).where(QuestionnaireVersion.is_current.is_(True))
    )
    return row.scalar_one()


async def _outcome_area_id(db_session) -> int:
    """id тестовой области «ОР / навык» (её сидит фикстура db_engine)."""
    row = await db_session.execute(select(OutcomeArea.id))
    return row.scalars().first()


async def _seed_two_questions(db_session) -> None:
    """2 критерия по одному вопросу: базовый + возрастной (9–11).

    Раньше это была ОДНА компетенция с базовым и условным вопросом. Теперь
    возраст — свойство критерия, поэтому условный вопрос обязан жить в своём:
    критерий показывается целиком либо не показывается вовсе.
    """
    area_id = await _outcome_area_id(db_session)
    base = Competency(code="C1", name="Базовый критерий", order=1, outcome_area_id=area_id)
    # Тот же порог, что у «Исследования профессиональных возможностей».
    conditional = Competency(
        code="C2",
        name="Возрастной критерий",
        order=2,
        outcome_area_id=area_id,
        min_grade=9,
        max_grade=11,
    )
    db_session.add_all([base, conditional])
    await db_session.flush()
    version_id = await _current_version_id(db_session)
    db_session.add_all(
        [
            Question(competency_id=base.id, text="базовый", order=0, version_id=version_id),
            Question(competency_id=conditional.id, text="условный", order=0, version_id=version_id),
        ]
    )
    await db_session.commit()


async def _setup_scenario(client: AsyncClient, headers: dict, grade: int) -> dict:
    """Класс заданного грейда: ученик s1 (+ второй s2 для полноты), учитель t1."""
    tag = f"g{grade}"
    s1 = await _register(client, f"s1_{tag}@vektor.ru", "student")
    s2 = await _register(client, f"s2_{tag}@vektor.ru", "student")
    cls = (
        await client.post("/classes", json={"grade": grade, "section": "a"}, headers=headers)
    ).json()
    await client.post(
        f"/classes/{cls['id']}/students", json={"student_ids": [s1, s2]}, headers=headers
    )
    return {"class_id": cls["id"], "s1": s1, "s2": s2, "s1_email": f"s1_{tag}@vektor.ru"}


async def _self_assessment_id(db_session, subject_id: int) -> int:
    row = await db_session.execute(
        select(Assessment.id).where(
            Assessment.respondent_id == subject_id, Assessment.subject_id == subject_id
        )
    )
    return row.scalar_one()


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    login = await client.post("/auth/login", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_get_assessment_not_found(client: AsyncClient, admin_headers) -> None:
    response = await client.get("/assessments/99999", headers=admin_headers)
    assert response.status_code == 404


async def test_get_assessment_forbidden_for_non_owner(
    client: AsyncClient, admin_headers, db_session
) -> None:
    setup = await _setup_scenario(client, admin_headers, grade=10)
    cid = await _create_campaign(client, admin_headers)
    await client.post(
        f"/campaigns/{cid}/generate", json={"class_ids": [setup["class_id"]]}, headers=admin_headers
    )
    aid = await _self_assessment_id(db_session, setup["s1"])  # анкета s1 про s1

    # s2 пытается открыть анкету s1 — не свою.
    s2_headers = await _login(client, "s2_g10@vektor.ru")
    response = await client.get(f"/assessments/{aid}", headers=s2_headers)
    assert response.status_code == 403


async def test_get_assessment_grade_10_sees_all_questions(
    client: AsyncClient, admin_headers, db_session
) -> None:
    await _seed_two_questions(db_session)
    setup = await _setup_scenario(client, admin_headers, grade=10)
    cid = await _create_campaign(client, admin_headers)
    await client.post(
        f"/campaigns/{cid}/generate", json={"class_ids": [setup["class_id"]]}, headers=admin_headers
    )
    aid = await _self_assessment_id(db_session, setup["s1"])

    headers = await _login(client, setup["s1_email"])
    response = await client.get(f"/assessments/{aid}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["subject"]["id"] == setup["s1"]
    # грейд 10 → видны оба вопроса (базовый + условный), ответов ещё нет.
    assert len(body["questions"]) == 2
    assert all(q["value"] is None for q in body["questions"])


async def test_get_assessment_grade_7_hides_conditional(
    client: AsyncClient, admin_headers, db_session
) -> None:
    await _seed_two_questions(db_session)
    setup = await _setup_scenario(client, admin_headers, grade=7)
    cid = await _create_campaign(client, admin_headers)
    await client.post(
        f"/campaigns/{cid}/generate", json={"class_ids": [setup["class_id"]]}, headers=admin_headers
    )
    aid = await _self_assessment_id(db_session, setup["s1"])

    headers = await _login(client, setup["s1_email"])
    response = await client.get(f"/assessments/{aid}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    # грейд 7 → условный вопрос скрыт, остаётся только базовый.
    assert len(body["questions"]) == 1
    assert body["questions"][0]["is_conditional"] is False


async def test_other_questionnaire_version_does_not_leak_into_campaign(
    client: AsyncClient, admin_headers, db_session
) -> None:
    """РЕГРЕССИЯ: анкета показывает вопросы ТОЛЬКО своей редакции.

    Архивная редакция (миграция c3f81ad0e7b5) добавляет в таблицу questions
    второй комплект вопросов на те же компетенции. Без фильтра по
    campaign.questionnaire_version_id действующая кампания начала бы отдавать
    оба комплекта разом.
    """
    await _seed_two_questions(db_session)

    # Архивная редакция со своим вопросом — на ту же компетенцию.
    archive = QuestionnaireVersion(code="archive-test", title="Архивная редакция")
    db_session.add(archive)
    await db_session.flush()
    competency_id = (await db_session.execute(select(Competency.id))).scalars().first()
    db_session.add(
        Question(
            competency_id=competency_id,
            text="архивный",
            order=0,
            version_id=archive.id,
        )
    )
    await db_session.commit()

    setup = await _setup_scenario(client, admin_headers, grade=10)
    cid = await _create_campaign(client, admin_headers)
    await client.post(
        f"/campaigns/{cid}/generate", json={"class_ids": [setup["class_id"]]}, headers=admin_headers
    )
    aid = await _self_assessment_id(db_session, setup["s1"])

    headers = await _login(client, setup["s1_email"])
    body = (await client.get(f"/assessments/{aid}", headers=headers)).json()

    # Ровно 2 вопроса действующей редакции, архивного среди них нет.
    assert len(body["questions"]) == 2
    assert all(q["text"] != "архивный" for q in body["questions"])


async def test_conditional_questions_survive_class_transfer(
    client: AsyncClient, admin_headers, db_session
) -> None:
    """РЕГРЕССИЯ: видимость вопросов считается по классу НА МОМЕНТ ГЕНЕРАЦИИ.

    Перевод ученика из 8-го в 9-й — штатное ежегодное событие. Раньше класс
    брался из текущего User.school_class, и после перевода в прошлогодней
    анкете задним числом «появлялся» условный вопрос: она переставала быть
    completed, а прогресс менялся сам собой. Пара к
    test_rater_role_survives_class_transfer в test_results.py.
    """
    await _seed_two_questions(db_session)
    setup = await _setup_scenario(client, admin_headers, grade=8)
    cid = await _create_campaign(client, admin_headers)
    await client.post(
        f"/campaigns/{cid}/generate", json={"class_ids": [setup["class_id"]]}, headers=admin_headers
    )
    aid = await _self_assessment_id(db_session, setup["s1"])
    headers = await _login(client, setup["s1_email"])

    before = (await client.get(f"/assessments/{aid}", headers=headers)).json()
    assert len(before["questions"]) == 1  # 8 класс → условный скрыт

    # НОВЫЙ УЧЕБНЫЙ ГОД: админ переводит ученика в 9-й класс.
    new_class = (
        await client.post("/classes", json={"grade": 9, "section": "б"}, headers=admin_headers)
    ).json()
    await client.post(
        f"/classes/{new_class['id']}/students",
        json={"student_ids": [setup["s1"]]},
        headers=admin_headers,
    )

    after = (await client.get(f"/assessments/{aid}", headers=headers)).json()
    # Прошлая анкета не переписана: условный вопрос в ней так и не появился.
    assert len(after["questions"]) == 1
    assert after["questions"][0]["is_conditional"] is False


# --- 4d: сохранение ответов (POST /assessments/{id}/answers) ---
from vektor.modules.assessments.service import compute_status  # noqa: E402
from vektor.shared.enums import CampaignStatus  # noqa: E402


@pytest.mark.parametrize(
    ("answered", "total", "expected"),
    [
        (0, 5, "not_started"),
        (3, 5, "in_progress"),
        (5, 5, "completed"),
        (0, 0, "completed"),  # нет видимых вопросов — заполнять нечего
    ],
)
def test_compute_status(answered: int, total: int, expected: str) -> None:
    assert compute_status(answered, total) == expected


async def _submit(client: AsyncClient, aid: int, headers: dict, answers: list[dict]) -> object:
    return await client.post(
        f"/assessments/{aid}/answers", json={"answers": answers}, headers=headers
    )


async def test_submit_answers_completes_assessment(
    client: AsyncClient, admin_headers, db_session
) -> None:
    await _seed_two_questions(db_session)
    setup = await _setup_scenario(client, admin_headers, grade=10)
    cid = await _create_campaign(client, admin_headers)
    await client.post(
        f"/campaigns/{cid}/generate", json={"class_ids": [setup["class_id"]]}, headers=admin_headers
    )
    aid = await _self_assessment_id(db_session, setup["s1"])
    headers = await _login(client, setup["s1_email"])

    detail = (await client.get(f"/assessments/{aid}", headers=headers)).json()
    question_ids = [q["id"] for q in detail["questions"]]

    response = await _submit(
        client, aid, headers, [{"question_id": qid, "value": 4} for qid in question_ids]
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["answered_questions"] == 2
    assert body["total_questions"] == 2


async def test_submit_answers_partial_is_in_progress(
    client: AsyncClient, admin_headers, db_session
) -> None:
    await _seed_two_questions(db_session)
    setup = await _setup_scenario(client, admin_headers, grade=10)
    cid = await _create_campaign(client, admin_headers)
    await client.post(
        f"/campaigns/{cid}/generate", json={"class_ids": [setup["class_id"]]}, headers=admin_headers
    )
    aid = await _self_assessment_id(db_session, setup["s1"])
    headers = await _login(client, setup["s1_email"])

    detail = (await client.get(f"/assessments/{aid}", headers=headers)).json()
    first_question_id = detail["questions"][0]["id"]

    response = await _submit(client, aid, headers, [{"question_id": first_question_id, "value": 3}])

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["answered_questions"] == 1
    assert body["total_questions"] == 2


async def test_submit_answers_upsert_updates_existing_value(
    client: AsyncClient, admin_headers, db_session
) -> None:
    await _seed_two_questions(db_session)
    setup = await _setup_scenario(client, admin_headers, grade=10)
    cid = await _create_campaign(client, admin_headers)
    await client.post(
        f"/campaigns/{cid}/generate", json={"class_ids": [setup["class_id"]]}, headers=admin_headers
    )
    aid = await _self_assessment_id(db_session, setup["s1"])
    headers = await _login(client, setup["s1_email"])

    detail = (await client.get(f"/assessments/{aid}", headers=headers)).json()
    question_id = detail["questions"][0]["id"]

    await _submit(client, aid, headers, [{"question_id": question_id, "value": 2}])
    response = await _submit(client, aid, headers, [{"question_id": question_id, "value": 5}])

    assert response.status_code == 200
    assert response.json()["answered_questions"] == 1  # обновили, а не задвоили

    detail_after = (await client.get(f"/assessments/{aid}", headers=headers)).json()
    updated = next(q for q in detail_after["questions"] if q["id"] == question_id)
    assert updated["value"] == 5


async def test_submit_answers_forbidden_for_non_owner(
    client: AsyncClient, admin_headers, db_session
) -> None:
    await _seed_two_questions(db_session)
    setup = await _setup_scenario(client, admin_headers, grade=10)
    cid = await _create_campaign(client, admin_headers)
    await client.post(
        f"/campaigns/{cid}/generate", json={"class_ids": [setup["class_id"]]}, headers=admin_headers
    )
    aid = await _self_assessment_id(db_session, setup["s1"])  # анкета s1 про s1

    s2_headers = await _login(client, "s2_g10@vektor.ru")
    response = await _submit(client, aid, s2_headers, [{"question_id": 1, "value": 3}])

    assert response.status_code == 403


async def test_submit_answers_not_found(client: AsyncClient, admin_headers) -> None:
    headers = await _login(client, "admin@vektor.ru")
    response = await _submit(client, 99999, headers, [{"question_id": 1, "value": 3}])
    assert response.status_code == 404


async def test_submit_answers_rejects_hidden_question(
    client: AsyncClient, admin_headers, db_session
) -> None:
    await _seed_two_questions(db_session)
    setup = await _setup_scenario(client, admin_headers, grade=7)  # 7 класс — условный скрыт
    cid = await _create_campaign(client, admin_headers)
    await client.post(
        f"/campaigns/{cid}/generate", json={"class_ids": [setup["class_id"]]}, headers=admin_headers
    )
    aid = await _self_assessment_id(db_session, setup["s1"])
    headers = await _login(client, setup["s1_email"])

    # Скрытый вопрос ищем через критерий: возраст живёт там, а не на вопросе.
    conditional_question = await db_session.execute(
        select(Question).join(Competency).where(Competency.min_grade.is_not(None))
    )
    hidden_id = conditional_question.scalar_one().id

    response = await _submit(client, aid, headers, [{"question_id": hidden_id, "value": 3}])
    assert response.status_code == 422


async def test_submit_answers_rejects_when_campaign_not_active(
    client: AsyncClient, admin_headers, db_session
) -> None:
    await _seed_two_questions(db_session)
    setup = await _setup_scenario(client, admin_headers, grade=10)
    cid = await _create_campaign(client, admin_headers)
    await client.post(
        f"/campaigns/{cid}/generate", json={"class_ids": [setup["class_id"]]}, headers=admin_headers
    )
    aid = await _self_assessment_id(db_session, setup["s1"])
    headers = await _login(client, setup["s1_email"])

    campaign = await db_session.get(Campaign, cid)
    campaign.status = CampaignStatus.CLOSED
    await db_session.commit()

    detail = (await client.get(f"/assessments/{aid}", headers=headers)).json()
    question_id = detail["questions"][0]["id"]

    response = await _submit(client, aid, headers, [{"question_id": question_id, "value": 3}])
    assert response.status_code == 409


# --- 4e: листинг «мои анкеты» (GET /assessments) ---


async def test_list_assessments_returns_only_own(client: AsyncClient, scenario) -> None:
    cid = await _create_campaign(client, scenario["headers"])
    await client.post(
        f"/campaigns/{cid}/generate",
        json={"class_ids": [scenario["class_id"]]},
        headers=scenario["headers"],
    )

    t1_headers = await _login(client, "t1@vektor.ru")
    response = await client.get("/assessments", headers=t1_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2  # t1 → s1, t1 → s2
    subject_ids = {item["subject"]["id"] for item in body}
    assert subject_ids == {scenario["ids"]["s1"], scenario["ids"]["s2"]}
    assert all(item["is_self"] is False for item in body)


async def test_list_assessments_self_flag(client: AsyncClient, scenario) -> None:
    cid = await _create_campaign(client, scenario["headers"])
    await client.post(
        f"/campaigns/{cid}/generate",
        json={"class_ids": [scenario["class_id"]]},
        headers=scenario["headers"],
    )

    s1_headers = await _login(client, "s1@vektor.ru")
    response = await client.get("/assessments", headers=s1_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1  # только самооценка
    assert body[0]["is_self"] is True
    assert body[0]["campaign_title"] == "360 · июнь 2026"


async def test_list_assessments_filters_by_campaign(client: AsyncClient, scenario) -> None:
    cid1 = await _create_campaign(client, scenario["headers"])
    await client.post(
        f"/campaigns/{cid1}/generate",
        json={"class_ids": [scenario["class_id"]]},
        headers=scenario["headers"],
    )
    cid2 = (
        await client.post(
            "/campaigns",
            json={"title": "360 · сентябрь 2026", "period": "2026-09"},
            headers=scenario["headers"],
        )
    ).json()["id"]  # без generate — анкет под ней нет

    s1_headers = await _login(client, "s1@vektor.ru")
    matching = await client.get(f"/assessments?campaign_id={cid1}", headers=s1_headers)
    empty = await client.get(f"/assessments?campaign_id={cid2}", headers=s1_headers)

    assert len(matching.json()) == 1
    assert empty.json() == []


async def test_list_assessments_reflects_progress(
    client: AsyncClient, scenario, db_session
) -> None:
    await _seed_two_questions(db_session)
    cid = await _create_campaign(client, scenario["headers"])
    await client.post(
        f"/campaigns/{cid}/generate",
        json={"class_ids": [scenario["class_id"]]},
        headers=scenario["headers"],
    )

    s1_headers = await _login(client, "s1@vektor.ru")
    aid = await _self_assessment_id(db_session, scenario["ids"]["s1"])
    detail = (await client.get(f"/assessments/{aid}", headers=s1_headers)).json()
    question_id = detail["questions"][0]["id"]
    await _submit(client, aid, s1_headers, [{"question_id": question_id, "value": 4}])

    item = (await client.get("/assessments", headers=s1_headers)).json()[0]
    assert item["answered_questions"] == 1
    assert item["total_questions"] == 2
    assert item["status"] == "in_progress"
