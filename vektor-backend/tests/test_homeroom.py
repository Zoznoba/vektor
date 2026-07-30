# Интеграционные тесты классного руководителя (PUT /classes/{id}/homeroom).
# Использует фикстуру existing_class из conftest (класс + заголовки админа).

from httpx import AsyncClient


async def _register_teacher(client: AsyncClient, email: str = "uchitel@vektor.ru") -> int:
    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": "Козлов Роман",
            "role": "teacher",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_assign_homeroom(client: AsyncClient, existing_class: dict) -> None:
    teacher_id = await _register_teacher(client)

    response = await client.put(
        f"/classes/{existing_class['id']}/homeroom",
        json={"teacher_id": teacher_id},
        headers=existing_class["_headers"],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["homeroom_teacher"]["id"] == teacher_id
    # Кл.рук автоматически становится и учителем класса
    assert teacher_id in {t["id"] for t in body["teachers"]}


async def test_reassign_homeroom_replaces(client: AsyncClient, existing_class: dict) -> None:
    """Кл.рук один: назначение нового заменяет старого, но старый остаётся учителем."""
    first = await _register_teacher(client, "first@vektor.ru")
    second = await _register_teacher(client, "second@vektor.ru")
    url = f"/classes/{existing_class['id']}/homeroom"

    await client.put(url, json={"teacher_id": first}, headers=existing_class["_headers"])
    response = await client.put(
        url, json={"teacher_id": second}, headers=existing_class["_headers"]
    )

    body = response.json()
    assert body["homeroom_teacher"]["id"] == second
    assert {first, second} <= {t["id"] for t in body["teachers"]}


async def test_assign_homeroom_non_teacher_conflict(
    client: AsyncClient, existing_class: dict, register_user: dict[str, str]
) -> None:
    """Учеником класс руководить нельзя."""
    login = await client.post("/auth/login", json=register_user)
    me = await client.get(
        "/users/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    student_id = me.json()["id"]

    response = await client.put(
        f"/classes/{existing_class['id']}/homeroom",
        json={"teacher_id": student_id},
        headers=existing_class["_headers"],
    )

    assert response.status_code == 409


async def test_assign_homeroom_unknown_class_not_found(
    client: AsyncClient, existing_class: dict
) -> None:
    teacher_id = await _register_teacher(client)

    response = await client.put(
        "/classes/99999/homeroom",
        json={"teacher_id": teacher_id},
        headers=existing_class["_headers"],
    )

    assert response.status_code == 404


async def test_homeroom_visible_in_class_list(client: AsyncClient, existing_class: dict) -> None:
    teacher_id = await _register_teacher(client)
    await client.put(
        f"/classes/{existing_class['id']}/homeroom",
        json={"teacher_id": teacher_id},
        headers=existing_class["_headers"],
    )

    response = await client.get("/classes", headers=existing_class["_headers"])

    assert response.status_code == 200
    listed = next(c for c in response.json() if c["id"] == existing_class["id"])
    assert listed["homeroom_teacher"]["id"] == teacher_id
