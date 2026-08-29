# Интеграционные тесты cases: реальные HTTP-запросы, реальный Postgres
# (тестовая база через фикстуру client). admin_headers — в conftest.py.

import pytest
from httpx import AsyncClient


async def _register(client: AsyncClient, *, email: str, role: str) -> dict:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": "Тест", "role": role},
    )
    return response.json()


async def _login_headers(client: AsyncClient, *, email: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": "password123"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def existing_case(client: AsyncClient, admin_headers: dict[str, str]) -> dict:
    response = await client.post("/cases", json={"name": "Робототехника"}, headers=admin_headers)
    return response.json()


# --- POST /cases ---


async def test_create_case_success(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    response = await client.post(
        "/cases",
        json={"name": "Робототехника", "description": "Кружок про роботов"},
        headers=admin_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Робототехника"
    assert body["description"] == "Кружок про роботов"
    assert body["students"] == []
    assert body["teachers"] == []


async def test_create_case_duplicate_name_conflict(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    response = await client.post("/cases", json={"name": "Робототехника"}, headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["code"] == "case_already_exists"


async def test_create_case_requires_admin(client: AsyncClient) -> None:
    await _register(client, email="teacher@vektor.ru", role="teacher")
    headers = await _login_headers(client, email="teacher@vektor.ru")

    response = await client.post("/cases", json={"name": "Хор"}, headers=headers)

    assert response.status_code == 403


# --- GET /cases ---


async def test_list_cases_sorted_by_name(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """Порядок задан явно: без ORDER BY карточки прыгали бы между запросами."""
    for name in ("Хор", "Астрономия", "Робототехника"):
        await client.post("/cases", json={"name": name}, headers=admin_headers)

    response = await client.get("/cases", headers=admin_headers)

    assert response.status_code == 200
    assert [case["name"] for case in response.json()] == ["Астрономия", "Робототехника", "Хор"]


async def test_list_cases_allowed_for_teacher(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    await _register(client, email="teacher@vektor.ru", role="teacher")
    headers = await _login_headers(client, email="teacher@vektor.ru")

    response = await client.get("/cases", headers=headers)

    assert response.status_code == 200


async def test_list_cases_forbidden_for_student(client: AsyncClient) -> None:
    await _register(client, email="pupil@vektor.ru", role="student")
    headers = await _login_headers(client, email="pupil@vektor.ru")

    response = await client.get("/cases", headers=headers)

    assert response.status_code == 403


# --- PATCH /cases/{id} ---


async def test_update_case_renames(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    response = await client.patch(
        f"/cases/{existing_case['id']}", json={"name": "Робототехника+"}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Робототехника+"


async def test_update_case_keeps_own_name_without_conflict(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    """Переименование в СВОЁ же название не должно конфликтовать само с собой."""
    response = await client.patch(
        f"/cases/{existing_case['id']}", json={"name": "Робототехника"}, headers=admin_headers
    )

    assert response.status_code == 200


async def test_update_case_duplicate_name_conflict(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    other = await client.post("/cases", json={"name": "Хор"}, headers=admin_headers)

    response = await client.patch(
        f"/cases/{other.json()['id']}", json={"name": "Робототехника"}, headers=admin_headers
    )

    assert response.status_code == 409


async def test_update_case_omitted_field_is_untouched(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """Ключа нет в теле → «не трогать»; явный null → «стереть». Ровно то, ради
    чего роутер отдаёт в сервис model_dump(exclude_unset=True)."""
    created = await client.post(
        "/cases", json={"name": "Хор", "description": "Поём"}, headers=admin_headers
    )
    case_id = created.json()["id"]

    renamed = await client.patch(
        f"/cases/{case_id}", json={"name": "Большой хор"}, headers=admin_headers
    )
    assert renamed.json()["description"] == "Поём"

    cleared = await client.patch(
        f"/cases/{case_id}", json={"description": None}, headers=admin_headers
    )
    assert cleared.json()["description"] is None
    assert cleared.json()["name"] == "Большой хор"


async def test_update_case_not_found(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    response = await client.patch("/cases/999", json={"name": "Нет"}, headers=admin_headers)

    assert response.status_code == 404
    assert response.json()["code"] == "case_not_found"


# --- POST /cases/{id}/students и /teachers ---


async def test_assign_students_and_teachers(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    pupil_a = await _register(client, email="pupil-a@vektor.ru", role="student")
    pupil_b = await _register(client, email="pupil-b@vektor.ru", role="student")
    teacher = await _register(client, email="teacher@vektor.ru", role="teacher")
    case_id = existing_case["id"]

    students = await client.post(
        f"/cases/{case_id}/students",
        json={"user_ids": [pupil_a["id"], pupil_b["id"]]},
        headers=admin_headers,
    )
    assert students.status_code == 200
    assert {u["id"] for u in students.json()["students"]} == {pupil_a["id"], pupil_b["id"]}

    teachers = await client.post(
        f"/cases/{case_id}/teachers",
        json={"user_ids": [teacher["id"]]},
        headers=admin_headers,
    )
    assert teachers.status_code == 200
    body = teachers.json()
    # Разные проекции ОДНОЙ колонки users.case_id: ученики не должны утечь в
    # список учителей и наоборот.
    assert [u["id"] for u in body["teachers"]] == [teacher["id"]]
    assert {u["id"] for u in body["students"]} == {pupil_a["id"], pupil_b["id"]}


async def test_assign_students_is_idempotent(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    """Повторная привязка того, кто уже в ЭТОМ кейсе, — no-op, а не 409."""
    pupil = await _register(client, email="pupil@vektor.ru", role="student")
    case_id = existing_case["id"]
    payload = {"user_ids": [pupil["id"]]}

    await client.post(f"/cases/{case_id}/students", json=payload, headers=admin_headers)
    again = await client.post(f"/cases/{case_id}/students", json=payload, headers=admin_headers)

    assert again.status_code == 200
    assert [u["id"] for u in again.json()["students"]] == [pupil["id"]]


async def test_assign_student_with_teacher_role_conflict(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    teacher = await _register(client, email="teacher@vektor.ru", role="teacher")

    response = await client.post(
        f"/cases/{existing_case['id']}/students",
        json={"user_ids": [teacher["id"]]},
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "wrong_role"


async def test_assign_member_of_another_case_conflict(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    """Перевод между кейсами делается явно: сначала открепить, потом привязать.
    Молчаливое перевешивание выкинуло бы человека из прежнего кейса."""
    pupil = await _register(client, email="pupil@vektor.ru", role="student")
    other = await client.post("/cases", json={"name": "Хор"}, headers=admin_headers)
    await client.post(
        f"/cases/{existing_case['id']}/students",
        json={"user_ids": [pupil["id"]]},
        headers=admin_headers,
    )

    response = await client.post(
        f"/cases/{other.json()['id']}/students",
        json={"user_ids": [pupil["id"]]},
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "already_in_another_case"

    # И человек остался в ПЕРВОМ кейсе: отказ должен быть отказом, а не
    # наполовину выполненным переводом.
    still_there = await client.get("/cases", headers=admin_headers)
    by_name = {case["name"]: case for case in still_there.json()}
    assert [u["id"] for u in by_name["Робототехника"]["students"]] == [pupil["id"]]
    assert by_name["Хор"]["students"] == []


async def test_assign_nothing_is_written_when_one_id_is_bad(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    """Атомарность: валидируем всю пачку ДО записи, иначе часть людей осела бы
    в кейсе, а часть — нет (та же логика, что в bulk-загрузке Этапа 3.7)."""
    pupil = await _register(client, email="pupil@vektor.ru", role="student")
    case_id = existing_case["id"]

    response = await client.post(
        f"/cases/{case_id}/students",
        json={"user_ids": [pupil["id"], 999]},
        headers=admin_headers,
    )
    assert response.status_code == 404
    assert response.json()["code"] == "user_not_found"

    after = await client.get("/cases", headers=admin_headers)
    assert after.json()[0]["students"] == []


async def test_case_is_cross_grade(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    """Ученики из РАЗНЫХ классов в одном кейсе — это его смысл, а не краевой
    случай: кружок собирается через параллели."""
    pupil_a = await _register(client, email="pupil-a@vektor.ru", role="student")
    pupil_b = await _register(client, email="pupil-b@vektor.ru", role="student")
    class_5 = await client.post(
        "/classes", json={"grade": 5, "section": "a"}, headers=admin_headers
    )
    class_8 = await client.post(
        "/classes", json={"grade": 8, "section": "b"}, headers=admin_headers
    )
    await client.post(
        f"/classes/{class_5.json()['id']}/students",
        json={"student_ids": [pupil_a["id"]]},
        headers=admin_headers,
    )
    await client.post(
        f"/classes/{class_8.json()['id']}/students",
        json={"student_ids": [pupil_b["id"]]},
        headers=admin_headers,
    )

    response = await client.post(
        f"/cases/{existing_case['id']}/students",
        json={"user_ids": [pupil_a["id"], pupil_b["id"]]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert {u["id"] for u in response.json()["students"]} == {pupil_a["id"], pupil_b["id"]}


async def test_assign_requires_admin(client: AsyncClient, existing_case: dict) -> None:
    await _register(client, email="teacher@vektor.ru", role="teacher")
    headers = await _login_headers(client, email="teacher@vektor.ru")

    response = await client.post(
        f"/cases/{existing_case['id']}/students", json={"user_ids": []}, headers=headers
    )

    assert response.status_code == 403


# --- DELETE /cases/{id}/members/{user_id} ---


async def test_remove_member(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    pupil = await _register(client, email="pupil@vektor.ru", role="student")
    case_id = existing_case["id"]
    await client.post(
        f"/cases/{case_id}/students", json={"user_ids": [pupil["id"]]}, headers=admin_headers
    )

    response = await client.delete(f"/cases/{case_id}/members/{pupil['id']}", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["students"] == []


async def test_remove_member_not_in_case(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    pupil = await _register(client, email="pupil@vektor.ru", role="student")

    response = await client.delete(
        f"/cases/{existing_case['id']}/members/{pupil['id']}", headers=admin_headers
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_in_case"


async def test_removed_member_can_join_another_case(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    """Открепление действительно освобождает человека, а не только прячет из
    списка: после него привязка в другой кейс проходит без 409."""
    pupil = await _register(client, email="pupil@vektor.ru", role="student")
    other = await client.post("/cases", json={"name": "Хор"}, headers=admin_headers)
    await client.post(
        f"/cases/{existing_case['id']}/students",
        json={"user_ids": [pupil["id"]]},
        headers=admin_headers,
    )
    await client.delete(
        f"/cases/{existing_case['id']}/members/{pupil['id']}", headers=admin_headers
    )

    response = await client.post(
        f"/cases/{other.json()['id']}/students",
        json={"user_ids": [pupil["id"]]},
        headers=admin_headers,
    )

    assert response.status_code == 200


# --- DELETE /cases/{id} ---


async def test_delete_empty_case(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    response = await client.delete(f"/cases/{existing_case['id']}", headers=admin_headers)

    assert response.status_code == 204
    assert (await client.get("/cases", headers=admin_headers)).json() == []


async def test_delete_case_with_members_conflict(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    pupil = await _register(client, email="pupil@vektor.ru", role="student")
    case_id = existing_case["id"]
    await client.post(
        f"/cases/{case_id}/students", json={"user_ids": [pupil["id"]]}, headers=admin_headers
    )

    response = await client.delete(f"/cases/{case_id}", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["code"] == "case_not_empty"


async def test_delete_case_requires_admin(client: AsyncClient, existing_case: dict) -> None:
    await _register(client, email="teacher@vektor.ru", role="teacher")
    headers = await _login_headers(client, email="teacher@vektor.ru")

    response = await client.delete(f"/cases/{existing_case['id']}", headers=headers)

    assert response.status_code == 403


# --- POST /cases/{id}/members/detach (bulk) ---


async def test_remove_members_bulk(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    """Ученики и учителя откепляются одним вызовом: колонка users.case_id одна
    на обе роли, разводить два пути незачем."""
    pupil_a = await _register(client, email="pupil-a@vektor.ru", role="student")
    pupil_b = await _register(client, email="pupil-b@vektor.ru", role="student")
    tutor = await _register(client, email="tutor@vektor.ru", role="teacher")
    case_id = existing_case["id"]
    await client.post(
        f"/cases/{case_id}/students",
        json={"user_ids": [pupil_a["id"], pupil_b["id"]]},
        headers=admin_headers,
    )
    await client.post(
        f"/cases/{case_id}/teachers", json={"user_ids": [tutor["id"]]}, headers=admin_headers
    )

    response = await client.post(
        f"/cases/{case_id}/members/detach",
        json={"user_ids": [pupil_a["id"], pupil_b["id"], tutor["id"]]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["students"] == []
    assert response.json()["teachers"] == []


async def test_remove_members_bulk_is_atomic(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    """Чужой в списке — не открепляется НИКТО.

    Ради этого вся пачка и проверяется до записи: иначе выделение, разошедшееся
    с реальным составом, разобрало бы кейс наполовину.
    """
    pupil = await _register(client, email="pupil@vektor.ru", role="student")
    outsider = await _register(client, email="outsider@vektor.ru", role="student")
    case_id = existing_case["id"]
    await client.post(
        f"/cases/{case_id}/students", json={"user_ids": [pupil["id"]]}, headers=admin_headers
    )

    response = await client.post(
        f"/cases/{case_id}/members/detach",
        json={"user_ids": [pupil["id"], outsider["id"]]},
        headers=admin_headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "not_in_case"

    listed = await client.get("/cases", headers=admin_headers)
    kase = next(c for c in listed.json() if c["id"] == case_id)
    assert {u["id"] for u in kase["students"]} == {pupil["id"]}


async def test_remove_members_bulk_empty_list_is_noop(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    pupil = await _register(client, email="pupil@vektor.ru", role="student")
    case_id = existing_case["id"]
    await client.post(
        f"/cases/{case_id}/students", json={"user_ids": [pupil["id"]]}, headers=admin_headers
    )

    response = await client.post(
        f"/cases/{case_id}/members/detach", json={"user_ids": []}, headers=admin_headers
    )

    assert response.status_code == 200
    assert {u["id"] for u in response.json()["students"]} == {pupil["id"]}


async def test_remove_members_bulk_requires_admin(
    client: AsyncClient, admin_headers: dict[str, str], existing_case: dict
) -> None:
    await _register(client, email="teacher@vektor.ru", role="teacher")
    headers = await _login_headers(client, email="teacher@vektor.ru")

    response = await client.post(
        f"/cases/{existing_case['id']}/members/detach", json={"user_ids": []}, headers=headers
    )

    assert response.status_code == 403
