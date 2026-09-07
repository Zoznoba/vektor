# Этап: ежегодный перевод классов. Сверху — юнит-тесты чистой plan_promotion
# (без БД), снизу — интеграционные на /classes/promotion/* через реальный API.
#
# РЕГРЕССИОННЫЙ тест: test_promotion_preserves_assessment_snapshots — перевод
# не должен трогать снапшоты Assessment, иначе прошлые результаты и динамика
# «поедут» вместе со сменой текущего класса ученика.

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from vektor.modules.assessments.models import Assessment, Campaign
from vektor.modules.classes.models import PromotionRun
from vektor.modules.classes.promotion import (
    GRADUATION_GRADE,
    SchoolClassView,
    StudentView,
    default_target_section,
    plan_promotion,
)
from vektor.modules.competencies.models import QuestionnaireVersion
from vektor.modules.users.models import User
from vektor.shared.academic_year import academic_year_label
from vektor.shared.enums import CampaignStatus, RaterRole

# ---------------------------------------------------------------------------
# Юнит: default_target_section
# ---------------------------------------------------------------------------


def test_target_section_keeps_section_below_grade_10() -> None:
    assert default_target_section(7, "1") == "1"


def test_target_section_drops_section_entering_grade_10() -> None:
    # 9 → 10: параллелей нет, секция обнуляется.
    assert default_target_section(9, "2") == ""


def test_target_section_stays_empty_grade_10_to_11() -> None:
    assert default_target_section(10, "") == ""


# ---------------------------------------------------------------------------
# Юнит: plan_promotion
# ---------------------------------------------------------------------------


def _cls(id_: int, grade: int, section: str, *student_ids: int) -> SchoolClassView:
    return SchoolClassView(
        id=id_,
        grade=grade,
        section=section,
        students=tuple(StudentView(id=s, is_active=True) for s in student_ids),
    )


def test_plan_maps_grade_plus_one() -> None:
    plan = plan_promotion([_cls(1, 7, "1", 10, 11, 12)])

    assert len(plan.transitions) == 1
    t = plan.transitions[0]
    assert (t.target_grade, t.target_section) == (8, "1")
    assert t.target_class_id is None
    assert t.source_class_ids == (1,)
    assert t.moving_student_ids == (10, 11, 12)
    assert t.merge is False


def test_plan_grade_11_goes_to_graduating() -> None:
    plan = plan_promotion([_cls(1, GRADUATION_GRADE, "", 10, 11)])
    assert plan.transitions == ()
    assert plan.graduating[0].student_ids == (10, 11)


def test_plan_merges_two_ninth_classes_into_grade_10() -> None:
    plan = plan_promotion([_cls(1, 9, "1", 10, 11), _cls(2, 9, "2", 20, 21)])

    assert len(plan.transitions) == 1
    t = plan.transitions[0]
    assert (t.target_grade, t.target_section) == (10, "")
    assert set(t.source_class_ids) == {1, 2}
    assert set(t.moving_student_ids) == {10, 11, 20, 21}
    assert t.merge is True


def test_plan_skips_empty_classes() -> None:
    plan = plan_promotion([_cls(1, 7, "1")])
    assert plan.transitions == ()
    assert plan.skipped[0].class_id == 1
    assert plan.skipped[0].reason == "empty"


def test_plan_student_already_in_target_is_idempotent() -> None:
    # 5 уже сидит в существующем 8-1, 6 — ещё в 7-1.
    source = _cls(1, 7, "1", 5, 6)
    target = _cls(2, 8, "1", 5)
    plan = plan_promotion([source, target])

    t = plan.transitions[0]
    assert t.target_class_id == 2
    assert t.moving_student_ids == (6,)
    assert t.already_in_target_ids == (5,)
    # Целевой класс "уже был" только из-за переехавшего — это не merge.
    assert t.merge is False


def test_plan_inactive_students_do_not_move() -> None:
    source = SchoolClassView(
        id=1,
        grade=7,
        section="1",
        students=(StudentView(id=10, is_active=True), StudentView(id=11, is_active=False)),
    )
    plan = plan_promotion([source])
    assert plan.transitions[0].moving_student_ids == (10,)


def test_plan_section_override_changes_target() -> None:
    plan = plan_promotion([_cls(1, 7, "1", 10)], section_overrides={1: "2"})
    assert plan.transitions[0].target_section == "2"


def test_plan_moving_sets_are_disjoint() -> None:
    plan = plan_promotion(
        [
            _cls(1, 7, "1", 10, 11),
            _cls(2, 9, "1", 20),
            _cls(3, 9, "2", 21),
            _cls(4, GRADUATION_GRADE, "", 30),
        ]
    )

    seen: set[int] = set()
    for t in plan.transitions:
        ids = set(t.moving_student_ids)
        assert not (ids & seen)
        seen |= ids
    grads = {s for g in plan.graduating for s in g.student_ids}
    assert not (seen & grads)


# ---------------------------------------------------------------------------
# Интеграция
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


async def _make_class(client: AsyncClient, headers: dict, grade: int, section: str) -> int:
    r = await client.post("/classes", json={"grade": grade, "section": section}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _add_students(
    client: AsyncClient, headers: dict, class_id: int, *emails: str
) -> list[int]:
    r = await client.post(
        "/users/bulk",
        json={
            "users": [
                {"email": e, "full_name": "Ученик Тестов", "role": "student"} for e in emails
            ],
            "class_id": class_id,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return [u["id"] for u in r.json()["created"]]


def _current_year() -> str:
    from datetime import date

    return academic_year_label(date.today())


async def _user(db_session, user_id: int) -> User:
    return await db_session.get(User, user_id)


async def test_preview_returns_plan(client: AsyncClient, admin_headers: dict) -> None:
    src = await _make_class(client, admin_headers, 7, "1")
    await _add_students(client, admin_headers, src, "p7a@vektor.ru", "p7b@vektor.ru")

    r = await client.post("/classes/promotion/preview", json={}, headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["already_ran"] is False
    assert body["academic_year"] == _current_year()
    assert body["total_moving"] == 2
    assert body["classes_to_create"] == 1
    t = next(t for t in body["transitions"] if t["source_class_ids"] == [src])
    assert t["target_label"] == "8-1"
    assert t["target_class_id"] is None
    assert t["moving_count"] == 2


async def test_apply_moves_students_creates_classes_graduates_eleventh(
    client: AsyncClient, admin_headers: dict, db_session
) -> None:
    src = await _make_class(client, admin_headers, 7, "1")
    [s1, s2] = await _add_students(client, admin_headers, src, "a7a@vektor.ru", "a7b@vektor.ru")
    grad = await _make_class(client, admin_headers, 11, "")
    [g1] = await _add_students(client, admin_headers, grad, "a11@vektor.ru")

    r = await client.post(
        "/classes/promotion/apply",
        json={"confirm_academic_year": _current_year()},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["summary"] == {"moved": 2, "graduated": 1, "classes_created": 1}
    assert run["can_undo"] is True

    # ученики переехали в новый 8-1
    classes = (await client.get("/classes", headers=admin_headers)).json()
    new_8 = next(c for c in classes if c["grade"] == 8 and c["section"] == "1")
    assert {u["id"] for u in new_8["students"]} == {s1, s2}

    # выпускник деактивирован и откреплён
    graduate = await _user(db_session, g1)
    assert graduate.is_active is False
    assert graduate.school_class_id is None


async def test_apply_twice_same_year_conflicts(
    client: AsyncClient, admin_headers: dict
) -> None:
    src = await _make_class(client, admin_headers, 7, "1")
    await _add_students(client, admin_headers, src, "t7@vektor.ru")

    ok = await client.post(
        "/classes/promotion/apply",
        json={"confirm_academic_year": _current_year()},
        headers=admin_headers,
    )
    assert ok.status_code == 200

    again = await client.post(
        "/classes/promotion/apply",
        json={"confirm_academic_year": _current_year()},
        headers=admin_headers,
    )
    assert again.status_code == 409
    assert again.json()["code"] == "promotion_already_run"


async def test_apply_wrong_confirm_academic_year_rejected(
    client: AsyncClient, admin_headers: dict
) -> None:
    src = await _make_class(client, admin_headers, 7, "1")
    await _add_students(client, admin_headers, src, "w7@vektor.ru")

    r = await client.post(
        "/classes/promotion/apply",
        json={"confirm_academic_year": "2000/2001 учебный год"},
        headers=admin_headers,
    )
    assert r.status_code == 422
    assert r.json()["code"] == "promotion_confirm_mismatch"


async def test_apply_reuses_existing_target_class(
    client: AsyncClient, admin_headers: dict, db_session
) -> None:
    # Целевой 8-1 заранее создан админом — перевод переиспользует его, не плодит второй.
    src = await _make_class(client, admin_headers, 7, "1")
    dst = await _make_class(client, admin_headers, 8, "1")
    [s1, s2] = await _add_students(client, admin_headers, src, "i7a@vektor.ru", "i7b@vektor.ru")

    r = await client.post(
        "/classes/promotion/apply",
        json={"confirm_academic_year": _current_year()},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["summary"]["classes_created"] == 0

    assert (await _user(db_session, s1)).school_class_id == dst
    assert (await _user(db_session, s2)).school_class_id == dst


async def test_promotion_preserves_assessment_snapshots(
    client: AsyncClient, admin_headers: dict, db_session
) -> None:
    """РЕГРЕССИЯ. Смена текущего класса ученика не трогает snapshot прошлой
    анкеты — иначе прошлые результаты и динамика «поедут»."""
    src = await _make_class(client, admin_headers, 7, "1")
    [student_id] = await _add_students(client, admin_headers, src, "snap7@vektor.ru")

    version_id = await db_session.scalar(
        select(QuestionnaireVersion.id).where(QuestionnaireVersion.is_current.is_(True))
    )
    campaign = Campaign(
        title="360 · июнь 2025",
        period_year=2025,
        period_month=6,
        status=CampaignStatus.CLOSED,
        questionnaire_version_id=version_id,
    )
    db_session.add(campaign)
    await db_session.flush()
    assessment = Assessment(
        campaign_id=campaign.id,
        respondent_id=student_id,
        subject_id=student_id,
        rater_role=RaterRole.SELF,
        subject_class_id=src,
    )
    db_session.add(assessment)
    await db_session.commit()

    r = await client.post(
        "/classes/promotion/apply",
        json={"confirm_academic_year": _current_year()},
        headers=admin_headers,
    )
    assert r.status_code == 200

    await db_session.refresh(assessment)
    await db_session.refresh(await _user(db_session, student_id))
    assert assessment.subject_class_id == src  # snapshot неизменен
    assert (await _user(db_session, student_id)).school_class_id != src  # текущий — новый


async def test_undo_restores_membership_unless_campaign_created(
    client: AsyncClient, admin_headers: dict, db_session
) -> None:
    src = await _make_class(client, admin_headers, 7, "1")
    [s1] = await _add_students(client, admin_headers, src, "u7@vektor.ru")
    grad = await _make_class(client, admin_headers, 11, "")
    [g1] = await _add_students(client, admin_headers, grad, "u11@vektor.ru")

    run = (
        await client.post(
            "/classes/promotion/apply",
            json={"confirm_academic_year": _current_year()},
            headers=admin_headers,
        )
    ).json()

    undo = await client.post(
        f"/classes/promotion/{run['id']}/undo", headers=admin_headers
    )
    assert undo.status_code == 200
    assert undo.json()["undone_at"] is not None

    assert (await _user(db_session, s1)).school_class_id == src
    graduate = await _user(db_session, g1)
    assert graduate.is_active is True
    assert graduate.school_class_id == grad

    # заново применить можно (активного run за год больше нет)
    reapply = await client.post(
        "/classes/promotion/apply",
        json={"confirm_academic_year": _current_year()},
        headers=admin_headers,
    )
    assert reapply.status_code == 200
    run2_id = reapply.json()["id"]

    # после создания кампании откат заблокирован.
    # rollback: закрыть транзакцию db_session, начатую ранними чтениями, —
    # иначе Postgres now() у INSERT кампании будет временем ТОЙ транзакции
    # (до reapply), и created_at окажется меньше run.ran_at.
    await db_session.rollback()
    version_id = await db_session.scalar(
        select(QuestionnaireVersion.id).where(QuestionnaireVersion.is_current.is_(True))
    )
    db_session.add(
        Campaign(
            title="новая",
            period_year=2026,
            period_month=6,
            status=CampaignStatus.DRAFT,
            questionnaire_version_id=version_id,
        )
    )
    await db_session.commit()

    blocked = await client.post(
        f"/classes/promotion/{run2_id}/undo", headers=admin_headers
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "promotion_undo_blocked"


async def test_promotion_run_row_written(
    client: AsyncClient, admin_headers: dict, db_session
) -> None:
    src = await _make_class(client, admin_headers, 7, "1")
    await _add_students(client, admin_headers, src, "row7@vektor.ru")
    await client.post(
        "/classes/promotion/apply",
        json={"confirm_academic_year": _current_year()},
        headers=admin_headers,
    )
    rows = (await db_session.execute(select(PromotionRun))).scalars().all()
    assert len(rows) == 1
    assert rows[0].academic_year == _current_year()
    assert len(rows[0].snapshot) == 1
