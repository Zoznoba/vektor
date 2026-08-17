# Этап 7 — единый формат ошибок.
#
# Проверяем не «работает ли 404», а именно ФОРМУ ответа: она должна быть
# одинаковой независимо от того, кто ошибку возбудил — наш домен, зависимость
# FastAPI или валидация Pydantic. Фронт (api/client.ts) разбирает ровно её.

import pytest
from httpx import AsyncClient
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import async_sessionmaker

from vektor.core.errors import DomainError
from vektor.modules.competencies.models import QuestionnaireVersion


@pytest.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


# --- DomainError как класс ---


def test_domain_error_uses_class_message_by_default() -> None:
    class Sample(DomainError):
        status_code = 409
        code = "sample"
        message = "по умолчанию"

    assert Sample().message == "по умолчанию"
    assert str(Sample()) == "по умолчанию"


def test_domain_error_message_can_be_overridden_at_raise() -> None:
    # Одна и та же ошибка бывает про разное: CampaignNotActive — это и
    # «закрыть можно только активную», и «приём ответов закрыт».
    class Sample(DomainError):
        message = "по умолчанию"

    assert Sample("уточнение на месте").message == "уточнение на месте"


def test_domain_error_override_does_not_leak_to_class() -> None:
    # Переопределение — на экземпляре: иначе первое же уточнение испортило бы
    # сообщение для всех последующих возбуждений.
    class Sample(DomainError):
        message = "по умолчанию"

    Sample("разовое уточнение")
    assert Sample().message == "по умолчанию"


# --- Форма ответа ---


async def test_domain_error_response_shape(client: AsyncClient, admin_headers) -> None:
    response = await client.patch("/campaigns/99999/close", headers=admin_headers)

    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "Кампания не найдена"
    assert body["code"] == "campaign_not_found"
    assert "errors" not in body  # разбора по полям здесь нет


async def test_validation_error_detail_is_string_not_list(
    client: AsyncClient, admin_headers
) -> None:
    # РЕГРЕССИЯ: FastAPI по умолчанию кладёт в detail СПИСОК объектов, а фронт
    # показывает detail только если это строка — любая 422 выглядела как
    # «Ошибка запроса (422)» без объяснения.
    response = await client.post(
        "/campaigns", json={"title": "", "period": "2026"}, headers=admin_headers
    )

    assert response.status_code == 422
    body = response.json()
    assert isinstance(body["detail"], str)
    assert body["code"] == "validation_error"


async def test_validation_error_lists_offending_fields(client: AsyncClient, admin_headers) -> None:
    response = await client.post(
        "/campaigns", json={"title": "", "period": "2026"}, headers=admin_headers
    )

    body = response.json()
    fields = [e["field"] for e in body["errors"]]
    assert "body.title" in fields
    assert all("message" in e for e in body["errors"])


async def test_unauthorized_keeps_shape_and_challenge_header(client: AsyncClient) -> None:
    # 401 возбуждает зависимость FastAPI, а не наш домен — форма всё равно та же.
    # WWW-Authenticate обязан уцелеть, иначе ответ перестаёт быть корректным
    # challenge'ем.
    response = await client.get("/results/1")

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    body = response.json()
    assert isinstance(body["detail"], str)
    assert body["code"] == "unauthorized"


async def test_forbidden_from_require_role_keeps_shape(client: AsyncClient, register_user) -> None:
    login = await client.post("/auth/login", json=register_user)
    student_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.post(
        "/campaigns", json={"title": "X", "period": "2026"}, headers=student_headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


async def test_unknown_route_keeps_shape(client: AsyncClient) -> None:
    response = await client.get("/no-such-endpoint")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


# --- Ошибки, которые раньше падали в 500 ---


async def test_missing_current_version_gives_409_not_500(
    client: AsyncClient, admin_headers, db_session
) -> None:
    # РЕГРЕССИЯ: NoCurrentQuestionnaireVersion не ловил ни один роутер, и
    # вместо осмысленного ответа клиент получал Internal Server Error.
    await db_session.execute(sa_update(QuestionnaireVersion).values(is_current=False))
    await db_session.commit()

    response = await client.post(
        "/campaigns", json={"title": "360", "period": "2026"}, headers=admin_headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "no_current_questionnaire_version"


# --- Контекстные сообщения ---


async def test_same_error_carries_context_specific_message(
    client: AsyncClient, admin_headers
) -> None:
    # Кампания в draft: закрыть нельзя, и сообщение должно быть именно про
    # закрытие, а не общее «кампания не активна».
    campaign = (
        await client.post(
            "/campaigns", json={"title": "360", "period": "2026"}, headers=admin_headers
        )
    ).json()

    response = await client.patch(f"/campaigns/{campaign['id']}/close", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "Закрыть можно только активную кампанию"
    assert response.json()["code"] == "campaign_not_active"
