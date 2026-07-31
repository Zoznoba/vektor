# Юнит-тесты чистого доменного ядра build_pairs — матрица «кто кого оценивает»
# для одного класса. Без БД: гоняем на голых id.
#
# generate_assessments (оркестрация с БД) покрывается отдельно интеграционными
# тестами — тут только доменные правила.

import pytest
from httpx import AsyncClient

from vektor.modules.assessments.service import build_pairs


def test_self_assessment_always_present() -> None:
    # Самооценка (s, s) есть у каждого ученика — даже без родителей/учителей/пиров.
    pairs = build_pairs(student_ids=[1, 2, 3], parent_ids_by_student={}, teacher_ids=[])
    assert pairs == {(1, 1), (2, 2), (3, 3)}


def test_parent_evaluates_only_own_child() -> None:
    # Родитель 10 привязан к ученику 1, родитель 20 — к ученику 2.
    # Родитель оценивает ТОЛЬКО своего ребёнка, не весь класс.
    pairs = build_pairs(
        student_ids=[1, 2],
        parent_ids_by_student={1: [10], 2: [20]},
        teacher_ids=[],
    )
    assert (10, 1) in pairs
    assert (20, 2) in pairs
    assert (10, 2) not in pairs  # чужому ребёнку — нет
    assert (20, 1) not in pairs


def test_teacher_evaluates_every_student() -> None:
    # Учитель класса оценивает каждого ученика.
    pairs = build_pairs(student_ids=[1, 2], parent_ids_by_student={}, teacher_ids=[100])
    assert (100, 1) in pairs
    assert (100, 2) in pairs


def test_no_peers_by_default() -> None:
    # include_peers=False (по умолчанию): одноклассники друг друга НЕ оценивают.
    # В парах не должно быть (ученик -> другой ученик).
    students = [1, 2, 3]
    pairs = build_pairs(student_ids=students, parent_ids_by_student={}, teacher_ids=[])
    peer_pairs = {(r, s) for r in students for s in students if r != s}
    assert pairs & peer_pairs == set()


def test_peers_added_and_symmetric_when_flag_on() -> None:
    # include_peers=True: каждый ученик оценивает каждого другого, симметрично.
    students = [1, 2, 3]
    pairs = build_pairs(
        student_ids=students, parent_ids_by_student={}, teacher_ids=[], include_peers=True
    )
    expected_peers = {(r, s) for r in students for s in students if r != s}
    assert expected_peers <= pairs
    # Симметрия: если есть (1, 2), есть и (2, 1).
    for r, s in expected_peers:
        assert (s, r) in pairs


def test_peers_flag_only_adds_peers_nothing_else_changes() -> None:
    # Разница между True и False — РОВНО множество пиров, ничего лишнего.
    students = [1, 2]
    base = build_pairs(students, {1: [10]}, [20], include_peers=False)
    with_peers = build_pairs(students, {1: [10]}, [20], include_peers=True)
    assert with_peers - base == {(1, 2), (2, 1)}


def test_student_without_parents_does_not_crash() -> None:
    # Ученик 2 не в словаре родителей — .get(s, []) страхует, пары родителя нет.
    pairs = build_pairs(student_ids=[1, 2], parent_ids_by_student={1: [10]}, teacher_ids=[])
    assert (10, 1) in pairs
    # Единственная пара с субъектом 2 — его самооценка; чужих родителей ему не досталось.
    assert {(resp, subj) for resp, subj in pairs if subj == 2} == {(2, 2)}


def test_duplicate_collapses_via_set() -> None:
    # Один и тот же человек — и родитель ученика 1, и учитель класса (id=10).
    # Пара (10, 1) должна встретиться один раз (set схлопывает дубль).
    pairs = build_pairs(student_ids=[1], parent_ids_by_student={1: [10]}, teacher_ids=[10])
    assert pairs == {(1, 1), (10, 1)}


def test_empty_class_gives_empty_matrix() -> None:
    # Нет учеников — нет субъектов — пустая матрица (учителя без учеников не с кем).
    assert build_pairs(student_ids=[], parent_ids_by_student={}, teacher_ids=[42]) == set()


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
    assert pairs == expected


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

from vektor.modules.assessments.models import Assessment  # noqa: E402
from vektor.modules.assessments.service import is_question_visible  # noqa: E402
from vektor.modules.competencies.models import Competency, Question  # noqa: E402


@pytest.mark.parametrize(
    ("is_conditional", "grade", "expected"),
    [
        (False, 10, True),  # базовый — всегда виден
        (False, 7, True),
        (False, None, True),
        (True, 9, True),  # условный — границы 9..11 видимы
        (True, 10, True),
        (True, 11, True),
        (True, 8, False),  # ниже 9 — скрыт
        (True, 12, False),  # 12 класса не бывает, но правило строго 9..11
        (True, None, False),  # класс неизвестен — скрыт, без падения
    ],
)
def test_is_question_visible(is_conditional: bool, grade: int | None, expected: bool) -> None:
    assert is_question_visible(is_conditional, grade) is expected


@pytest.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


async def _seed_two_questions(db_session) -> None:
    """1 компетенция, 2 вопроса: базовый + условный (для 9–11)."""
    comp = Competency(code="C1", name="Компетенция 1", order=1)
    db_session.add(comp)
    await db_session.flush()
    db_session.add_all(
        [
            Question(competency_id=comp.id, text="базовый", is_conditional=False, order=1),
            Question(competency_id=comp.id, text="условный", is_conditional=True, order=2),
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
