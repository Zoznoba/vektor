# Интеграционные тесты auth: реальные HTTP-запросы к приложению,
# реальный Postgres (но тестовая база через фикстуру client).

from httpx import AsyncClient

from .conftest import REGISTER_DATA


async def test_register_creates_user(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json=REGISTER_DATA)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "petya@vektor.ru"
    assert body["role"] == "student"
    assert body["is_active"] is True


async def test_register_never_leaks_password(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json=REGISTER_DATA)

    # Ни пароля, ни хеша в ответе быть не должно — ни под каким именем.
    assert "password" not in response.json()
    assert "hashed_password" not in response.json()


async def test_register_duplicate_email_conflict(client: AsyncClient) -> None:
    await client.post("/auth/register", json=REGISTER_DATA)
    response = await client.post("/auth/register", json=REGISTER_DATA)

    assert response.status_code == 409


async def test_register_short_password_rejected(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json={**REGISTER_DATA, "password": "short"})

    assert response.status_code == 422


async def test_register_unknown_role_rejected(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json={**REGISTER_DATA, "role": "director"})

    assert response.status_code == 422


async def test_login_returns_token(client: AsyncClient, register_user: dict[str, str]) -> None:
    response = await client.post(
        "/auth/login",
        json={"email": register_user["email"], "password": register_user["password"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"].count(".") == 2  # форма JWT: header.payload.signature


async def test_login_wrong_password_unauthorized(
    client: AsyncClient, register_user: dict[str, str]
) -> None:
    response = await client.post(
        "/auth/login",
        json={"email": register_user["email"], "password": "wrong-password"},
    )

    assert response.status_code == 401


async def test_login_unknown_email_unauthorized(
    client: AsyncClient, register_user: dict[str, str]
) -> None:
    response = await client.post(
        "/auth/login",
        json={"email": "nobody@vektor.ru", "password": register_user["password"]},
    )

    assert response.status_code == 401


async def test_login_errors_are_indistinguishable(
    client: AsyncClient, register_user: dict[str, str]
) -> None:
    # Защита от перечисления пользователей: «нет такого email» и
    # «неверный пароль» должны быть неотличимы для клиента.

    wrong_password = await client.post(
        "/auth/login", json={"email": register_user["email"], "password": "wrong-password"}
    )
    unknown_email = await client.post(
        "/auth/login", json={"email": "nobody@vektor.ru", "password": register_user["password"]}
    )

    assert wrong_password.status_code == unknown_email.status_code
    assert wrong_password.json() == unknown_email.json()
