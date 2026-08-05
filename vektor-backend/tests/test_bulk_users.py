# Интеграционные тесты массовой загрузки (Этап 3.7): POST /users/bulk.
# Реальный HTTP + тестовый Postgres. admin_headers/existing_class — в conftest.py.

from httpx import AsyncClient

from vektor.core.config import settings


async def _login_headers(client: AsyncClient, *, email: str, password: str) -> dict[str, str]:
    response = await client.post("/auth/login", json={"email": email, "password": password})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _all_emails(client: AsyncClient, headers: dict[str, str]) -> set[str]:
    response = await client.get("/users", headers=headers)
    return {u["email"] for u in response.json()}


def _rows(*emails: str, role: str = "student") -> list[dict]:
    return [{"email": e, "full_name": "Тест Тестов", "role": role} for e in emails]


# --- happy path ---


async def test_bulk_create_without_class(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    payload = {"users": _rows("a@vektor.ru", "b@vektor.ru", "c@vektor.ru")}

    response = await client.post("/users/bulk", json=payload, headers=admin_headers)

    assert response.status_code == 201
    body = response.json()
    assert {u["email"] for u in body["created"]} == {"a@vektor.ru", "b@vektor.ru", "c@vektor.ru"}
    assert body["class_id"] is None
    assert body["default_password"] == settings.bulk_default_password
    # id проставлены (server_default подтянулся после commit)
    assert all(isinstance(u["id"], int) for u in body["created"])


async def test_bulk_created_user_can_login(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    payload = {"users": _rows("pupil@vektor.ru")}
    await client.post("/users/bulk", json=payload, headers=admin_headers)

    # Общий пароль реально работает — пользователь логинится им.
    login = await client.post(
        "/auth/login",
        json={"email": "pupil@vektor.ru", "password": settings.bulk_default_password},
    )
    assert login.status_code == 200
    assert "access_token" in login.json()


async def test_bulk_attaches_students_to_class(client: AsyncClient, existing_class: dict) -> None:
    headers = existing_class["_headers"]
    payload = {
        "class_id": existing_class["id"],
        "users": _rows("s1@vektor.ru", "s2@vektor.ru"),
    }

    response = await client.post("/users/bulk", json=payload, headers=headers)
    assert response.status_code == 201

    classes = await client.get("/classes", headers=headers)
    school_class = next(c for c in classes.json() if c["id"] == existing_class["id"])
    assert {s["email"] for s in school_class["students"]} == {"s1@vektor.ru", "s2@vektor.ru"}


async def test_bulk_non_students_not_attached_to_class(
    client: AsyncClient, existing_class: dict
) -> None:
    headers = existing_class["_headers"]
    payload = {
        "class_id": existing_class["id"],
        "users": [
            {"email": "kid@vektor.ru", "full_name": "Ученик", "role": "student"},
            {"email": "mom@vektor.ru", "full_name": "Родитель", "role": "parent"},
            {"email": "teach@vektor.ru", "full_name": "Учитель", "role": "teacher"},
        ],
    }

    response = await client.post("/users/bulk", json=payload, headers=headers)
    assert response.status_code == 201

    classes = await client.get("/classes", headers=headers)
    school_class = next(c for c in classes.json() if c["id"] == existing_class["id"])
    # К классу прицепился только ученик, родитель/учитель — нет.
    assert {s["email"] for s in school_class["students"]} == {"kid@vektor.ru"}


# --- атомарность: любая невалидная строка → в БД ничего ---


async def test_bulk_duplicate_in_batch_rejected_atomically(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    before = await _all_emails(client, admin_headers)
    payload = {"users": _rows("dup@vektor.ru", "ok@vektor.ru", "dup@vektor.ru")}

    response = await client.post("/users/bulk", json=payload, headers=admin_headers)

    assert response.status_code == 422
    # Ни один из присланных не осел, включая валидный "ok@vektor.ru".
    assert await _all_emails(client, admin_headers) == before


async def test_bulk_email_already_taken_rejected_atomically(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    # admin@vektor.ru уже существует (из фикстуры admin_headers).
    before = await _all_emails(client, admin_headers)
    payload = {"users": _rows("fresh@vektor.ru", "admin@vektor.ru")}

    response = await client.post("/users/bulk", json=payload, headers=admin_headers)

    assert response.status_code == 409
    # Свежий "fresh@vektor.ru" НЕ должен был создаться из-за конфликта соседа.
    assert await _all_emails(client, admin_headers) == before


async def test_bulk_class_not_found_rejected_atomically(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    before = await _all_emails(client, admin_headers)
    payload = {"class_id": 999999, "users": _rows("x@vektor.ru")}

    response = await client.post("/users/bulk", json=payload, headers=admin_headers)

    assert response.status_code == 404
    assert await _all_emails(client, admin_headers) == before


# --- права и валидация тела ---


async def test_bulk_empty_users_rejected(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.post("/users/bulk", json={"users": []}, headers=admin_headers)
    assert response.status_code == 422  # min_length=1 в схеме


async def test_bulk_forbidden_for_non_admin(client: AsyncClient) -> None:
    await client.post(
        "/auth/register",
        json={
            "email": "stud@vektor.ru",
            "password": "password123",
            "full_name": "Ученик",
            "role": "student",
        },
    )
    headers = await _login_headers(client, email="stud@vektor.ru", password="password123")

    response = await client.post(
        "/users/bulk", json={"users": _rows("y@vektor.ru")}, headers=headers
    )
    assert response.status_code == 403


async def test_bulk_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/users/bulk", json={"users": _rows("z@vektor.ru")})
    assert response.status_code == 401
