# Интеграционные тесты classes: реальные HTTP-запросы, реальный Postgres
# (тестовая база через фикстуру client). admin_headers/existing_class — в conftest.py.

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


# --- POST /classes ---


async def test_create_class_success(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    response = await client.post(
        "/classes", json={"grade": 5, "section": "b"}, headers=admin_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["grade"] == 5
    assert body["section"] == "b"
    assert body["students"] == []
    assert body["teachers"] == []


async def test_create_class_duplicate_conflict(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    payload = {"grade": 5, "section": "b"}
    await client.post("/classes", json=payload, headers=admin_headers)
    response = await client.post("/classes", json=payload, headers=admin_headers)

    assert response.status_code == 409


@pytest.mark.parametrize("invalid_grade", [0, 12])
async def test_create_class_invalid_grade_rejected(
    client: AsyncClient, admin_headers: dict[str, str], invalid_grade: int
) -> None:
    response = await client.post(
        "/classes", json={"grade": invalid_grade, "section": "b"}, headers=admin_headers
    )

    assert response.status_code == 422


async def test_create_class_forbidden_for_non_admin(client: AsyncClient) -> None:
    await _register(client, email="student@vektor.ru", role="student")
    headers = await _login_headers(client, email="student@vektor.ru")

    response = await client.post("/classes", json={"grade": 5, "section": "b"}, headers=headers)

    assert response.status_code == 403


async def test_create_class_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/classes", json={"grade": 5, "section": "b"})

    assert response.status_code == 401


# --- GET /classes ---


async def test_list_classes_as_admin(client: AsyncClient, existing_class: dict) -> None:
    response = await client.get("/classes", headers=existing_class["_headers"])

    assert response.status_code == 200
    ids = [c["id"] for c in response.json()]
    assert existing_class["id"] in ids


async def test_list_classes_as_teacher_allowed(client: AsyncClient, existing_class: dict) -> None:
    await _register(client, email="teacher@vektor.ru", role="teacher")
    teacher_headers = await _login_headers(client, email="teacher@vektor.ru")

    response = await client.get("/classes", headers=teacher_headers)

    assert response.status_code == 200


async def test_list_classes_forbidden_for_student(client: AsyncClient) -> None:
    await _register(client, email="student@vektor.ru", role="student")
    headers = await _login_headers(client, email="student@vektor.ru")

    response = await client.get("/classes", headers=headers)

    assert response.status_code == 403


async def test_list_classes_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/classes")

    assert response.status_code == 401


async def test_list_classes_empty_by_default(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.get("/classes", headers=admin_headers)

    assert response.status_code == 200
    assert response.json() == []


# --- POST /classes/{class_id}/students ---


async def test_assign_one_student(client: AsyncClient, existing_class: dict) -> None:
    student = await _register(client, email="pupil1@vektor.ru", role="student")

    response = await client.post(
        f"/classes/{existing_class['id']}/students",
        json={"student_ids": [student["id"]]},
        headers=existing_class["_headers"],
    )

    assert response.status_code == 200
    assert [s["id"] for s in response.json()["students"]] == [student["id"]]


async def test_assign_multiple_students(client: AsyncClient, existing_class: dict) -> None:
    pupil_a = await _register(client, email="pupil-a@vektor.ru", role="student")
    pupil_b = await _register(client, email="pupil-b@vektor.ru", role="student")

    response = await client.post(
        f"/classes/{existing_class['id']}/students",
        json={"student_ids": [pupil_a["id"], pupil_b["id"]]},
        headers=existing_class["_headers"],
    )

    assert response.status_code == 200
    assigned_ids = {s["id"] for s in response.json()["students"]}
    assert assigned_ids == {pupil_a["id"], pupil_b["id"]}


async def test_assign_students_class_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    student = await _register(client, email="pupil1@vektor.ru", role="student")

    response = await client.post(
        "/classes/999999/students",
        json={"student_ids": [student["id"]]},
        headers=admin_headers,
    )

    assert response.status_code == 404


async def test_assign_students_atomic_on_missing_id(
    client: AsyncClient, existing_class: dict
) -> None:
    pupil = await _register(client, email="pupil1@vektor.ru", role="student")

    response = await client.post(
        f"/classes/{existing_class['id']}/students",
        json={"student_ids": [pupil["id"], 999999]},
        headers=existing_class["_headers"],
    )
    assert response.status_code == 404

    # Ключевая проверка "всё или ничего": реальный ученик НЕ должен был
    # прицепиться к классу из-за того, что в том же запросе был битый id.
    classes = await client.get("/classes", headers=existing_class["_headers"])
    school_class = next(c for c in classes.json() if c["id"] == existing_class["id"])
    assert pupil["id"] not in [s["id"] for s in school_class["students"]]


async def test_assign_students_forbidden_for_non_admin(
    client: AsyncClient, existing_class: dict
) -> None:
    pupil = await _register(client, email="pupil1@vektor.ru", role="student")
    pupil_headers = await _login_headers(client, email="pupil1@vektor.ru")

    response = await client.post(
        f"/classes/{existing_class['id']}/students",
        json={"student_ids": [pupil["id"]]},
        headers=pupil_headers,
    )

    assert response.status_code == 403


# --- POST /classes/{class_id}/teachers ---


async def test_assign_one_teacher(client: AsyncClient, existing_class: dict) -> None:
    teacher = await _register(client, email="teacher1@vektor.ru", role="teacher")

    response = await client.post(
        f"/classes/{existing_class['id']}/teachers",
        json={"teacher_ids": [teacher["id"]]},
        headers=existing_class["_headers"],
    )

    assert response.status_code == 200
    assert [t["id"] for t in response.json()["teachers"]] == [teacher["id"]]


async def test_assign_multiple_teachers(client: AsyncClient, existing_class: dict) -> None:
    teacher_a = await _register(client, email="teacher-a@vektor.ru", role="teacher")
    teacher_b = await _register(client, email="teacher-b@vektor.ru", role="teacher")

    response = await client.post(
        f"/classes/{existing_class['id']}/teachers",
        json={"teacher_ids": [teacher_a["id"], teacher_b["id"]]},
        headers=existing_class["_headers"],
    )

    assert response.status_code == 200
    assigned_ids = {t["id"] for t in response.json()["teachers"]}
    assert assigned_ids == {teacher_a["id"], teacher_b["id"]}


async def test_assign_teacher_duplicate_conflict(client: AsyncClient, existing_class: dict) -> None:
    teacher = await _register(client, email="teacher1@vektor.ru", role="teacher")
    payload = {"teacher_ids": [teacher["id"]]}
    headers = existing_class["_headers"]

    await client.post(f"/classes/{existing_class['id']}/teachers", json=payload, headers=headers)
    response = await client.post(
        f"/classes/{existing_class['id']}/teachers", json=payload, headers=headers
    )

    assert response.status_code == 409


async def test_assign_teachers_class_not_found(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    teacher = await _register(client, email="teacher1@vektor.ru", role="teacher")

    response = await client.post(
        "/classes/999999/teachers",
        json={"teacher_ids": [teacher["id"]]},
        headers=admin_headers,
    )

    assert response.status_code == 404


async def test_assign_teachers_user_not_found(client: AsyncClient, existing_class: dict) -> None:
    response = await client.post(
        f"/classes/{existing_class['id']}/teachers",
        json={"teacher_ids": [999999]},
        headers=existing_class["_headers"],
    )

    assert response.status_code == 404


async def test_assign_teachers_forbidden_for_non_admin(
    client: AsyncClient, existing_class: dict
) -> None:
    teacher = await _register(client, email="teacher1@vektor.ru", role="teacher")
    teacher_headers = await _login_headers(client, email="teacher1@vektor.ru")

    response = await client.post(
        f"/classes/{existing_class['id']}/teachers",
        json={"teacher_ids": [teacher["id"]]},
        headers=teacher_headers,
    )

    assert response.status_code == 403
