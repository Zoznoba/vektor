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
