# Конструктор анкеты (Этап 7): черновик редакции, CRUD глав/критериев/
# вопросов, публикация. Интеграционные тесты через реальный API — доменной
# логики без БД тут почти нет (```_move``` — единственная чистая-ish функция,
# но она сама ходит в БД за соседями, поэтому тестируется тоже через API).

from httpx import AsyncClient


async def _create_draft(client: AsyncClient, headers: dict[str, str]) -> dict:
    response = await client.post("/questionnaire-versions/draft", headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _add_area(
    client: AsyncClient, headers: dict[str, str], version_id: int, name: str
) -> dict:
    response = await client.post(
        f"/questionnaire-versions/{version_id}/outcome-areas",
        json={"name": name},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _add_competency(
    client: AsyncClient, headers: dict[str, str], version_id: int, area_id: int, name: str
) -> dict:
    response = await client.post(
        f"/questionnaire-versions/{version_id}/outcome-areas/{area_id}/competencies",
        json={"name": name},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _add_question(
    client: AsyncClient, headers: dict[str, str], version_id: int, competency_id: int, text: str
) -> dict:
    response = await client.post(
        f"/questionnaire-versions/{version_id}/competencies/{competency_id}/questions",
        json={"text": text},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_list_versions_includes_seeded_current(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.get("/questionnaire-versions", headers=admin_headers)
    assert response.status_code == 200
    codes = [v["code"] for v in response.json()]
    assert "test-current" in codes


async def test_non_admin_cannot_list_versions(client: AsyncClient, register_user: dict) -> None:
    login = await client.post("/auth/login", json=register_user)
    token = login.json()["access_token"]
    response = await client.get(
        "/questionnaire-versions", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


async def test_create_draft_clones_questions_and_rejects_second_draft(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    draft = await _create_draft(client, admin_headers)
    assert draft["status"] == "draft"
    assert draft["is_current"] is False

    again = await client.post("/questionnaire-versions/draft", headers=admin_headers)
    assert again.status_code == 409
    assert again.json()["code"] == "draft_already_exists"


async def test_full_build_and_publish_flow(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    draft = await _create_draft(client, admin_headers)
    version_id = draft["id"]

    area = await _add_area(client, admin_headers, version_id, "Личное самоопределение")
    assert area["is_draft"] is True

    competency = await _add_competency(
        client, admin_headers, version_id, area["id"], "Самосознание"
    )
    assert competency["is_draft"] is True

    question = await _add_question(
        client, admin_headers, version_id, competency["id"], "Я знаю свои сильные стороны"
    )
    assert question["order"] == 0

    question_2 = await _add_question(
        client, admin_headers, version_id, competency["id"], "Я знаю свои слабые стороны"
    )
    assert question_2["order"] == 1

    # Дерево отражает добавленное.
    tree = await client.get(f"/questionnaire-versions/{version_id}/tree", headers=admin_headers)
    assert tree.status_code == 200
    tree_areas = tree.json()["outcome_areas"]
    added = next(a for a in tree_areas if a["id"] == area["id"])
    assert [q["text"] for q in added["competencies"][0]["questions"]] == [
        "Я знаю свои сильные стороны",
        "Я знаю свои слабые стороны",
    ]

    # move: вторая позиция уходит на первую.
    moved = await client.patch(
        f"/questions/{question_2['id']}/move", json={"direction": "up"}, headers=admin_headers
    )
    assert moved.status_code == 200
    assert moved.json()["order"] == 0

    publish = await client.post(
        f"/questionnaire-versions/{version_id}/publish", headers=admin_headers
    )
    assert publish.status_code == 200
    published = publish.json()
    assert published["status"] == "published"
    assert published["is_current"] is True

    # Старая действующая редакция больше не is_current, но никуда не делась.
    versions = (await client.get("/questionnaire-versions", headers=admin_headers)).json()
    old = next(v for v in versions if v["code"] == "test-current")
    assert old["is_current"] is False
    assert old["status"] == "published"

    # После публикации структура заморожена: ни редактировать, ни добавлять нельзя.
    frozen_edit = await client.patch(
        f"/questions/{question['id']}", json={"text": "переписано"}, headers=admin_headers
    )
    assert frozen_edit.status_code == 409
    assert frozen_edit.json()["code"] == "questionnaire_version_not_draft"

    frozen_add = await client.post(
        f"/questionnaire-versions/{version_id}/outcome-areas",
        json={"name": "Новая глава"},
        headers=admin_headers,
    )
    assert frozen_add.status_code == 409


async def test_publish_rejects_empty_draft(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    draft = await _create_draft(client, admin_headers)
    response = await client.post(
        f"/questionnaire-versions/{draft['id']}/publish", headers=admin_headers
    )
    assert response.status_code == 409
    assert response.json()["code"] == "empty_questionnaire"


async def test_discard_draft_removes_draft_only_rows(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    draft = await _create_draft(client, admin_headers)
    version_id = draft["id"]
    area = await _add_area(client, admin_headers, version_id, "Временная глава")

    discard = await client.delete(f"/questionnaire-versions/{version_id}", headers=admin_headers)
    assert discard.status_code == 204

    versions = (await client.get("/questionnaire-versions", headers=admin_headers)).json()
    assert draft["id"] not in [v["id"] for v in versions]

    # Черновая область удалена вместе с черновиком — новый черновик её не увидит.
    new_draft = await _create_draft(client, admin_headers)
    tree = await client.get(
        f"/questionnaire-versions/{new_draft['id']}/tree", headers=admin_headers
    )
    assert area["id"] not in [a["id"] for a in tree.json()["outcome_areas"]]


async def test_archive_applies_immediately_without_draft(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    draft = await _create_draft(client, admin_headers)
    area = await _add_area(client, admin_headers, draft["id"], "Область под архив")

    archived = await client.patch(
        f"/outcome-areas/{area['id']}/archive", json={"is_archived": True}, headers=admin_headers
    )
    assert archived.status_code == 200
    assert archived.json()["is_archived"] is True

    restored = await client.patch(
        f"/outcome-areas/{area['id']}/archive", json={"is_archived": False}, headers=admin_headers
    )
    assert restored.json()["is_archived"] is False
