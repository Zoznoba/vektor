# Интеграционные тесты классного руководства и предметной роли учителя.
# С Этапа 7m руководителей может быть НЕСКОЛЬКО: это флаг is_homeroom на
# связке «учитель ↔ класс», а не отдельный FK на классе.
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


def _link(body: dict, teacher_id: int) -> dict:
    return next(t for t in body["teachers"] if t["teacher"]["id"] == teacher_id)


def _homeroom_ids(body: dict) -> set[int]:
    return {t["teacher"]["id"] for t in body["teachers"] if t["is_homeroom"]}


async def test_assign_teacher_as_homeroom(client: AsyncClient, existing_class: dict) -> None:
    teacher_id = await _register_teacher(client)

    response = await client.post(
        f"/classes/{existing_class['id']}/teachers",
        json={"teacher_ids": [teacher_id], "is_homeroom": True},
        headers=existing_class["_headers"],
    )

    assert response.status_code == 200
    body = response.json()
    assert _homeroom_ids(body) == {teacher_id}
    # Кл.рук по построению числится и среди учителей класса — это одна строка
    assert _link(body, teacher_id)["is_homeroom"] is True


async def test_class_can_have_several_homerooms(client: AsyncClient, existing_class: dict) -> None:
    """Ровно то, ради чего менялась модель: руководителей может быть больше одного."""
    first = await _register_teacher(client, "first@vektor.ru")
    second = await _register_teacher(client, "second@vektor.ru")

    await client.post(
        f"/classes/{existing_class['id']}/teachers",
        json={"teacher_ids": [first, second]},
        headers=existing_class["_headers"],
    )
    for teacher_id in (first, second):
        response = await client.patch(
            f"/classes/{existing_class['id']}/teachers/{teacher_id}",
            json={"is_homeroom": True},
            headers=existing_class["_headers"],
        )
        assert response.status_code == 200

    assert _homeroom_ids(response.json()) == {first, second}


async def test_subject_lives_on_the_link_not_on_the_teacher(
    client: AsyncClient, existing_class: dict
) -> None:
    """Один учитель — разные предметы в разных классах."""
    teacher_id = await _register_teacher(client)
    headers = existing_class["_headers"]

    other = await client.post("/classes", json={"grade": 5, "section": "z"}, headers=headers)
    other_id = other.json()["id"]

    await client.post(
        f"/classes/{existing_class['id']}/teachers",
        json={"teacher_ids": [teacher_id], "subject": "литература"},
        headers=headers,
    )
    second = await client.post(
        f"/classes/{other_id}/teachers",
        json={"teacher_ids": [teacher_id], "subject": "русский язык"},
        headers=headers,
    )

    assert second.status_code == 200
    listed = {c["id"]: c for c in (await client.get("/classes", headers=headers)).json()}
    assert _link(listed[existing_class["id"]], teacher_id)["subject"] == "литература"
    assert _link(listed[other_id], teacher_id)["subject"] == "русский язык"


async def test_patch_subject_keeps_homeroom(client: AsyncClient, existing_class: dict) -> None:
    """Частичная правка: поле, которого нет в теле, не трогается."""
    teacher_id = await _register_teacher(client)
    headers = existing_class["_headers"]
    await client.post(
        f"/classes/{existing_class['id']}/teachers",
        json={"teacher_ids": [teacher_id], "subject": "физика", "is_homeroom": True},
        headers=headers,
    )

    response = await client.patch(
        f"/classes/{existing_class['id']}/teachers/{teacher_id}",
        json={"subject": "астрономия"},
        headers=headers,
    )

    link = _link(response.json(), teacher_id)
    assert link["subject"] == "астрономия"
    assert link["is_homeroom"] is True


async def test_patch_explicit_null_clears_subject(
    client: AsyncClient, existing_class: dict
) -> None:
    """А явный null — стирает: это отличается от «поле не передали»."""
    teacher_id = await _register_teacher(client)
    headers = existing_class["_headers"]
    await client.post(
        f"/classes/{existing_class['id']}/teachers",
        json={"teacher_ids": [teacher_id], "subject": "физика"},
        headers=headers,
    )

    response = await client.patch(
        f"/classes/{existing_class['id']}/teachers/{teacher_id}",
        json={"subject": None},
        headers=headers,
    )

    assert _link(response.json(), teacher_id)["subject"] is None


async def test_remove_teacher_drops_homeroom_too(client: AsyncClient, existing_class: dict) -> None:
    teacher_id = await _register_teacher(client)
    headers = existing_class["_headers"]
    await client.post(
        f"/classes/{existing_class['id']}/teachers",
        json={"teacher_ids": [teacher_id], "is_homeroom": True},
        headers=headers,
    )

    response = await client.delete(
        f"/classes/{existing_class['id']}/teachers/{teacher_id}", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["teachers"] == []


async def test_remove_teacher_not_in_class_404(client: AsyncClient, existing_class: dict) -> None:
    teacher_id = await _register_teacher(client)

    response = await client.delete(
        f"/classes/{existing_class['id']}/teachers/{teacher_id}",
        headers=existing_class["_headers"],
    )

    assert response.status_code == 404


async def test_assign_non_teacher_conflict(
    client: AsyncClient, existing_class: dict, register_user: dict[str, str]
) -> None:
    """Учеником класс руководить нельзя — и просто «вести» тоже."""
    login = await client.post("/auth/login", json=register_user)
    me = await client.get(
        "/users/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )

    response = await client.post(
        f"/classes/{existing_class['id']}/teachers",
        json={"teacher_ids": [me.json()["id"]], "is_homeroom": True},
        headers=existing_class["_headers"],
    )

    assert response.status_code == 409


async def test_homeroom_visible_in_class_list(client: AsyncClient, existing_class: dict) -> None:
    teacher_id = await _register_teacher(client)
    await client.post(
        f"/classes/{existing_class['id']}/teachers",
        json={"teacher_ids": [teacher_id], "subject": "история", "is_homeroom": True},
        headers=existing_class["_headers"],
    )

    response = await client.get("/classes", headers=existing_class["_headers"])

    assert response.status_code == 200
    listed = next(c for c in response.json() if c["id"] == existing_class["id"])
    assert _homeroom_ids(listed) == {teacher_id}
    assert _link(listed, teacher_id)["subject"] == "история"


async def test_remove_student_from_class(client: AsyncClient, existing_class: dict) -> None:
    headers = existing_class["_headers"]
    created = await client.post(
        "/users/bulk",
        json={
            "users": [{"email": "vybyl@vektor.ru", "full_name": "Иванов Иван", "role": "student"}],
            "class_id": existing_class["id"],
        },
        headers=headers,
    )
    student_id = created.json()["created"][0]["id"]

    response = await client.delete(
        f"/classes/{existing_class['id']}/students/{student_id}", headers=headers
    )

    assert response.status_code == 200
    assert response.json()["students"] == []
    # Сам пользователь остался в системе — открепление это не удаление
    listed = await client.get("/users", headers=headers)
    assert student_id in {u["id"] for u in listed.json()}


async def test_remove_student_from_wrong_class_404(
    client: AsyncClient, existing_class: dict
) -> None:
    headers = existing_class["_headers"]
    created = await client.post(
        "/users/bulk",
        json={
            "users": [
                {"email": "svoboden@vektor.ru", "full_name": "Петров Пётр", "role": "student"}
            ]
        },
        headers=headers,
    )
    student_id = created.json()["created"][0]["id"]

    response = await client.delete(
        f"/classes/{existing_class['id']}/students/{student_id}", headers=headers
    )

    assert response.status_code == 404
