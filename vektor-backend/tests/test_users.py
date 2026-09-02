# Интеграционные тесты GET /users: список + фильтры (Этап 7, аналитика).

import pytest
from httpx import AsyncClient


async def _register(client: AsyncClient, email: str, role: str, full_name: str) -> int:
    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": full_name,
            "role": role,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
async def roster(client: AsyncClient, admin_headers: dict[str, str]) -> dict:
    """Класс с двумя учениками + учитель + родитель, вне класса."""
    class_response = await client.post(
        "/classes", json={"grade": 8, "section": "1"}, headers=admin_headers
    )
    class_id = class_response.json()["id"]

    ivanova = await _register(client, "ivanova@vektor.ru", "student", "Иванова Полина")
    petrov = await _register(client, "petrov@vektor.ru", "student", "Петров Олег")
    other_student = await _register(client, "sidorov@vektor.ru", "student", "Сидоров Ким")
    teacher = await _register(client, "teach@vektor.ru", "teacher", "Козлов Р.С.")
    await _register(client, "parent@vektor.ru", "parent", "Смирнова М.П.")

    await client.post(
        f"/classes/{class_id}/students",
        json={"student_ids": [ivanova, petrov]},
        headers=admin_headers,
    )

    return {
        "class_id": class_id,
        "ivanova": ivanova,
        "petrov": petrov,
        "other_student": other_student,
        "teacher": teacher,
    }


async def test_list_users_no_filters_returns_all(
    client: AsyncClient, admin_headers: dict[str, str], roster: dict
) -> None:
    response = await client.get("/users", headers=admin_headers)

    assert response.status_code == 200
    # admin сам плюс 5 заведённых в фикстуре.
    assert len(response.json()) == 6


async def test_list_users_filter_by_role(
    client: AsyncClient, admin_headers: dict[str, str], roster: dict
) -> None:
    response = await client.get("/users", params={"role": "student"}, headers=admin_headers)

    assert response.status_code == 200
    assert {u["id"] for u in response.json()} == {
        roster["ivanova"],
        roster["petrov"],
        roster["other_student"],
    }


async def test_list_users_filter_by_search_matches_name(
    client: AsyncClient, admin_headers: dict[str, str], roster: dict
) -> None:
    response = await client.get("/users", params={"search": "иванов"}, headers=admin_headers)

    assert response.status_code == 200
    ids = {u["id"] for u in response.json()}
    assert ids == {roster["ivanova"]}


async def test_list_users_filter_by_search_matches_email_case_insensitive(
    client: AsyncClient, admin_headers: dict[str, str], roster: dict
) -> None:
    response = await client.get("/users", params={"search": "PETROV@"}, headers=admin_headers)

    assert response.status_code == 200
    assert {u["id"] for u in response.json()} == {roster["petrov"]}


async def test_list_users_filter_by_class_id(
    client: AsyncClient, admin_headers: dict[str, str], roster: dict
) -> None:
    response = await client.get(
        "/users", params={"class_id": roster["class_id"]}, headers=admin_headers
    )

    assert response.status_code == 200
    assert {u["id"] for u in response.json()} == {roster["ivanova"], roster["petrov"]}


async def test_list_users_combined_filters(
    client: AsyncClient, admin_headers: dict[str, str], roster: dict
) -> None:
    response = await client.get(
        "/users",
        params={"role": "student", "class_id": roster["class_id"], "search": "олег"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert {u["id"] for u in response.json()} == {roster["petrov"]}


async def test_list_users_requires_admin(client: AsyncClient, roster: dict) -> None:
    login = await client.post(
        "/auth/login", json={"email": "teach@vektor.ru", "password": "password123"}
    )
    teacher_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.get("/users", headers=teacher_headers)

    assert response.status_code == 403


async def test_deactivate_user_blocks_login(
    client: AsyncClient, admin_headers: dict[str, str], roster: dict
) -> None:
    response = await client.patch(
        f"/users/{roster['teacher']}/active", json={"is_active": False}, headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False

    login = await client.post(
        "/auth/login", json={"email": "teach@vektor.ru", "password": "password123"}
    )
    assert login.status_code == 401


async def test_reactivate_user_restores_login(
    client: AsyncClient, admin_headers: dict[str, str], roster: dict
) -> None:
    await client.patch(
        f"/users/{roster['teacher']}/active", json={"is_active": False}, headers=admin_headers
    )

    response = await client.patch(
        f"/users/{roster['teacher']}/active", json={"is_active": True}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is True

    login = await client.post(
        "/auth/login", json={"email": "teach@vektor.ru", "password": "password123"}
    )
    assert login.status_code == 200


async def test_cannot_deactivate_self(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    me = await client.get("/users/me", headers=admin_headers)
    admin_id = me.json()["id"]

    response = await client.patch(
        f"/users/{admin_id}/active", json={"is_active": False}, headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "cannot_modify_self"


async def test_deactivate_nonexistent_user_404(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.patch(
        "/users/999999/active", json={"is_active": False}, headers=admin_headers
    )

    assert response.status_code == 404


async def test_deactivate_user_requires_admin(client: AsyncClient, roster: dict) -> None:
    login = await client.post(
        "/auth/login", json={"email": "teach@vektor.ru", "password": "password123"}
    )
    teacher_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.patch(
        f"/users/{roster['ivanova']}/active", json={"is_active": False}, headers=teacher_headers
    )

    assert response.status_code == 403


async def test_reset_password_returns_new_password_and_allows_login(
    client: AsyncClient, admin_headers: dict[str, str], roster: dict
) -> None:
    response = await client.post(
        f"/users/{roster['teacher']}/reset-password", headers=admin_headers
    )

    assert response.status_code == 200
    new_password = response.json()["new_password"]
    assert len(new_password) >= 8

    # старый пароль больше не подходит
    old_login = await client.post(
        "/auth/login", json={"email": "teach@vektor.ru", "password": "password123"}
    )
    assert old_login.status_code == 401

    # новый — подходит
    new_login = await client.post(
        "/auth/login", json={"email": "teach@vektor.ru", "password": new_password}
    )
    assert new_login.status_code == 200


async def test_reset_password_nonexistent_user_404(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post("/users/999999/reset-password", headers=admin_headers)

    assert response.status_code == 404


async def test_reset_password_requires_admin(client: AsyncClient, roster: dict) -> None:
    login = await client.post(
        "/auth/login", json={"email": "teach@vektor.ru", "password": "password123"}
    )
    teacher_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.post(
        f"/users/{roster['ivanova']}/reset-password", headers=teacher_headers
    )

    assert response.status_code == 403


# --- Фильтры по кейсу (Этап 8) ---


@pytest.fixture
async def roster_with_case(
    client: AsyncClient, admin_headers: dict[str, str], roster: dict
) -> dict:
    """Поверх roster: кейс, в котором лежит один ученик и один учитель."""
    kase = (await client.post("/cases", json={"name": "Хор"}, headers=admin_headers)).json()
    await client.post(
        f"/cases/{kase['id']}/students",
        json={"user_ids": [roster["ivanova"]]},
        headers=admin_headers,
    )
    await client.post(
        f"/cases/{kase['id']}/teachers",
        json={"user_ids": [roster["teacher"]]},
        headers=admin_headers,
    )
    return {**roster, "case_id": kase["id"]}


async def test_list_users_filter_by_case_id(
    client: AsyncClient, admin_headers: dict[str, str], roster_with_case: dict
) -> None:
    """Фильтр по кейсу отдаёт весь его состав — и учеников, и учителей: колонка
    users.case_id одна на обе роли."""
    response = await client.get(
        f"/users?case_id={roster_with_case['case_id']}", headers=admin_headers
    )

    assert response.status_code == 200
    assert {u["id"] for u in response.json()} == {
        roster_with_case["ivanova"],
        roster_with_case["teacher"],
    }


async def test_list_users_without_case_excludes_members(
    client: AsyncClient, admin_headers: dict[str, str], roster_with_case: dict
) -> None:
    """`without_case` — это список кандидатов на привязку: членство в кейсе
    одно, и человека из другого кейса бэкенд не примет."""
    response = await client.get("/users?without_case=true&role=student", headers=admin_headers)

    ids = {u["id"] for u in response.json()}
    assert roster_with_case["ivanova"] not in ids
    assert {roster_with_case["petrov"], roster_with_case["other_student"]} <= ids


async def test_list_users_exposes_case_id(
    client: AsyncClient, admin_headers: dict[str, str], roster_with_case: dict
) -> None:
    """case_id виден в общем списке — иначе экран пользователей не показал бы
    кейс, не запрашивая состав каждого кейса отдельно."""
    response = await client.get("/users?role=student", headers=admin_headers)

    by_id = {u["id"]: u for u in response.json()}
    assert by_id[roster_with_case["ivanova"]]["case_id"] == roster_with_case["case_id"]
    assert by_id[roster_with_case["petrov"]]["case_id"] is None


async def test_me_exposes_case_name(
    client: AsyncClient, admin_headers: dict[str, str], roster_with_case: dict
) -> None:
    """Название кейса человеку отдаёт /users/me — в шапку, как и класс."""
    login = await client.post(
        "/auth/login", json={"email": "ivanova@vektor.ru", "password": "password123"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.get("/users/me", headers=headers)

    assert response.status_code == 200
    assert response.json()["case_name"] == "Хор"
