# Интеграционные тесты связи родитель—ребёнок (Этап 3.6).
# Всё через реальный API: регистрация участников, привязка админом, проверки.

import pytest
from httpx import AsyncClient


async def _register(client: AsyncClient, email: str, role: str) -> int:
    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": f"Тест {role}",
            "role": role,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
async def family(client: AsyncClient) -> dict[str, int]:
    """Родитель и двое детей-учеников."""
    return {
        "parent": await _register(client, "mama@vektor.ru", "parent"),
        "child1": await _register(client, "syn@vektor.ru", "student"),
        "child2": await _register(client, "doch@vektor.ru", "student"),
    }


async def test_assign_children_bulk(client: AsyncClient, admin_headers, family) -> None:
    response = await client.post(
        f"/users/{family['parent']}/children",
        json={"child_ids": [family["child1"], family["child2"]]},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == family["parent"]
    assert {c["id"] for c in body["children"]} == {family["child1"], family["child2"]}


async def test_assign_children_idempotent(client: AsyncClient, admin_headers, family) -> None:
    """Повторная привязка того же ребёнка — не ошибка и не дубль."""
    for _ in range(2):
        response = await client.post(
            f"/users/{family['parent']}/children",
            json={"child_ids": [family["child1"]]},
            headers=admin_headers,
        )
        assert response.status_code == 200

    assert len(response.json()["children"]) == 1


async def test_get_children(client: AsyncClient, admin_headers, family) -> None:
    await client.post(
        f"/users/{family['parent']}/children",
        json={"child_ids": [family["child1"]]},
        headers=admin_headers,
    )

    response = await client.get(f"/users/{family['parent']}/children", headers=admin_headers)

    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == [family["child1"]]


async def test_assign_to_non_parent_conflict(client: AsyncClient, admin_headers, family) -> None:
    """Привязать детей можно только к родителю — к ученику нельзя."""
    response = await client.post(
        f"/users/{family['child1']}/children",
        json={"child_ids": [family["child2"]]},
        headers=admin_headers,
    )

    assert response.status_code == 409


async def test_assign_non_student_child_conflict(
    client: AsyncClient, admin_headers, family
) -> None:
    """Ребёнком может быть только ученик — не второй родитель."""
    other_parent = await _register(client, "papa@vektor.ru", "parent")

    response = await client.post(
        f"/users/{family['parent']}/children",
        json={"child_ids": [other_parent]},
        headers=admin_headers,
    )

    assert response.status_code == 409


async def test_assign_unknown_child_not_found(client: AsyncClient, admin_headers, family) -> None:
    response = await client.post(
        f"/users/{family['parent']}/children",
        json={"child_ids": [99999]},
        headers=admin_headers,
    )

    assert response.status_code == 404


async def test_assign_children_requires_admin(client: AsyncClient, family) -> None:
    """Без токена админа привязка запрещена."""
    login = await client.post(
        "/auth/login", json={"email": "mama@vektor.ru", "password": "password123"}
    )
    parent_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.post(
        f"/users/{family['parent']}/children",
        json={"child_ids": [family["child1"]]},
        headers=parent_headers,
    )

    assert response.status_code == 403


async def test_get_children_self_access_for_parent(
    client: AsyncClient, admin_headers, family
) -> None:
    """Родитель может получить СВОИХ детей без админа — нужно для кабинета родителя."""
    await client.post(
        f"/users/{family['parent']}/children",
        json={"child_ids": [family["child1"], family["child2"]]},
        headers=admin_headers,
    )

    login = await client.post(
        "/auth/login", json={"email": "mama@vektor.ru", "password": "password123"}
    )
    parent_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.get(f"/users/{family['parent']}/children", headers=parent_headers)

    assert response.status_code == 200
    assert {c["id"] for c in response.json()} == {family["child1"], family["child2"]}


async def test_get_children_forbidden_for_other_parent(
    client: AsyncClient, admin_headers, family
) -> None:
    """Родитель НЕ может заглянуть в детей другого родителя по его id."""
    await client.post(
        f"/users/{family['parent']}/children",
        json={"child_ids": [family["child1"]]},
        headers=admin_headers,
    )
    other_parent_id = await _register(client, "papa2@vektor.ru", "parent")

    login = await client.post(
        "/auth/login", json={"email": "papa2@vektor.ru", "password": "password123"}
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.get(f"/users/{family['parent']}/children", headers=other_headers)

    assert response.status_code == 403


async def test_get_children_forbidden_for_student_self(
    client: AsyncClient, admin_headers, family
) -> None:
    """Самодоступ работает только для роли PARENT, не для любого «своего» id."""
    login = await client.post(
        "/auth/login", json={"email": "syn@vektor.ru", "password": "password123"}
    )
    student_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.get(f"/users/{family['child1']}/children", headers=student_headers)

    assert response.status_code == 403
