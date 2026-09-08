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
    assert [t["teacher"]["id"] for t in response.json()["teachers"]] == [teacher["id"]]


async def test_assign_multiple_teachers(client: AsyncClient, existing_class: dict) -> None:
    teacher_a = await _register(client, email="teacher-a@vektor.ru", role="teacher")
    teacher_b = await _register(client, email="teacher-b@vektor.ru", role="teacher")

    response = await client.post(
        f"/classes/{existing_class['id']}/teachers",
        json={"teacher_ids": [teacher_a["id"], teacher_b["id"]]},
        headers=existing_class["_headers"],
    )

    assert response.status_code == 200
    assigned_ids = {t["teacher"]["id"] for t in response.json()["teachers"]}
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


# --- PATCH /classes/{id} и DELETE /classes/{id} -----------------------------
# Скелеты под срез «инструменты класса у админа». Тела дописать после
# реализации service.update_class / service.delete_class.


async def test_update_class_changes_grade_and_section(
    client: AsyncClient, existing_class: dict
) -> None:
    # TODO: PATCH /classes/{id} с {"grade": 8, "section": "c"} → 200,
    #   в ответе новые grade/section, состав не потерян.
    ...


async def test_update_class_partial_keeps_untouched_field(
    client: AsyncClient, existing_class: dict
) -> None:
    # TODO: PATCH только с {"section": "d"} → grade остаётся прежним
    #   (exclude_unset: ключа нет = «не трогать»).
    ...


async def test_update_class_duplicate_pair_conflict(
    client: AsyncClient, admin_headers: dict[str, str], existing_class: dict
) -> None:
    # TODO: создать второй класс (8, "a"); PATCH первого в (8, "a") → 409.
    ...


async def test_update_class_forbidden_for_non_admin(
    client: AsyncClient, existing_class: dict
) -> None:
    # TODO: учитель/ученик → 403.
    ...


async def test_delete_empty_class(client: AsyncClient, existing_class: dict) -> None:
    # TODO: DELETE пустого класса → 204; GET /classes больше его не содержит.
    ...


async def test_delete_class_with_students_conflict(
    client: AsyncClient, existing_class: dict
) -> None:
    # TODO: привязать ученика, DELETE → 409, класс на месте.
    ...


async def test_delete_class_with_diagnostics_history_conflict(
    client: AsyncClient, existing_class: dict
) -> None:
    # TODO: самый важный кейс — класс без людей, но с анкетой, у которой
    #   subject_class_id == этот класс (снапшот). DELETE → 409, а не 500.
    #   Проще всего собрать через фикстуры assessments/results; если дорого —
    #   вставить Assessment напрямую в тестовую сессию.
    ...


async def test_delete_class_forbidden_for_non_admin(
    client: AsyncClient, existing_class: dict
) -> None:
    # TODO: учитель/ученик → 403.
    ...
