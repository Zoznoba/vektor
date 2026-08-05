# Этап 5 — результаты. Сверху юнит-тесты чистых доменных функций (без БД),
# снизу интеграционные на GET /results/{subject_id} через реальный API.
#
# Два теста помечены как РЕГРЕССИОННЫЕ — они закрывают ошибки, найденные при
# перепроверке среза 5b/5c:
#   1) порог анонимности считался глобально («ответил хоть что-нибудь»), из-за
#      чего компетенцию с ответом ОДНОГО одноклассника показывали;
#   2) роль оценивающего выводилась из ТЕКУЩЕГО состава класса, из-за чего
#      перевод ученика в другой класс переписывал прошлые результаты.

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from vektor.modules.assessments.models import Assessment
from vektor.modules.competencies.models import (
    Competency,
    OutcomeArea,
    Question,
    QuestionnaireVersion,
)
from vektor.modules.results.service import (
    ScoredAnswer,
    aggregate_by_competency_and_rater,
    can_disclose_peer_scores,
    can_view_results,
    compute_gap,
    count_peer_raters_by_competency,
    others_by_competency,
    overall_by_competency,
    pick_growth_zones,
    redact_peer_scores,
    self_by_competency,
)
from vektor.shared.enums import RaterRole, UserRole


def _peer(competency_id: int, respondent_id: int, value: int) -> ScoredAnswer:
    return ScoredAnswer(
        competency_id=competency_id,
        rater_role=RaterRole.PEER,
        respondent_id=respondent_id,
        value=value,
    )


# --- can_disclose_peer_scores ---


def test_cannot_disclose_below_threshold() -> None:
    assert can_disclose_peer_scores(2) is False


def test_can_disclose_at_threshold() -> None:
    assert can_disclose_peer_scores(3) is True


def test_can_disclose_above_threshold() -> None:
    assert can_disclose_peer_scores(4) is True


def test_can_disclose_custom_threshold() -> None:
    assert can_disclose_peer_scores(4, threshold=5) is False
    assert can_disclose_peer_scores(5, threshold=5) is True


# --- count_peer_raters_by_competency ---


def test_counts_distinct_peers_not_answers() -> None:
    # Один и тот же одноклассник ответил на 3 вопроса одной компетенции —
    # это ОДИН человек, а не три. Иначе порог обходился бы в одиночку.
    answers = [_peer(1, respondent_id=7, value=v) for v in (1, 2, 3)]
    assert count_peer_raters_by_competency(answers) == {1: 1}


def test_counts_peers_per_competency_separately() -> None:
    answers = [_peer(1, 7, 4), _peer(1, 8, 4), _peer(2, 9, 4)]
    assert count_peer_raters_by_competency(answers) == {1: 2, 2: 1}


def test_counts_ignore_non_peer_roles() -> None:
    answers = [
        ScoredAnswer(competency_id=1, rater_role=RaterRole.TEACHER, respondent_id=7, value=4),
        ScoredAnswer(competency_id=1, rater_role=RaterRole.SELF, respondent_id=1, value=4),
    ]
    assert count_peer_raters_by_competency(answers) == {}


# --- aggregate_by_competency_and_rater ---


def test_aggregate_averages_multiple_answers_same_role() -> None:
    answers = [_peer(1, 7, 3), _peer(1, 8, 5)]
    assert aggregate_by_competency_and_rater(answers) == {1: {RaterRole.PEER: 4.0}}


def test_aggregate_keeps_competencies_and_roles_separate() -> None:
    answers = [
        ScoredAnswer(competency_id=1, rater_role=RaterRole.SELF, respondent_id=1, value=4),
        ScoredAnswer(competency_id=1, rater_role=RaterRole.TEACHER, respondent_id=9, value=2),
        ScoredAnswer(competency_id=2, rater_role=RaterRole.SELF, respondent_id=1, value=5),
    ]
    assert aggregate_by_competency_and_rater(answers) == {
        1: {RaterRole.SELF: 4.0, RaterRole.TEACHER: 2.0},
        2: {RaterRole.SELF: 5.0},
    }


def test_aggregate_empty_answers() -> None:
    assert aggregate_by_competency_and_rater([]) == {}


# --- redact_peer_scores (единая точка правила анонимности) ---


def test_redact_removes_peer_below_threshold() -> None:
    scores = {1: {RaterRole.SELF: 4.0, RaterRole.PEER: 2.0}}
    assert redact_peer_scores(scores, {1: 2}) == {1: {RaterRole.SELF: 4.0}}


def test_redact_keeps_peer_at_threshold() -> None:
    scores = {1: {RaterRole.SELF: 4.0, RaterRole.PEER: 2.0}}
    assert redact_peer_scores(scores, {1: 3}) == {1: {RaterRole.SELF: 4.0, RaterRole.PEER: 2.0}}


def test_redact_is_per_competency() -> None:
    # РЕГРЕССИЯ: раньше решение было одно на все компетенции. Теперь у
    # компетенции 1 (два пира) балл прячется, у компетенции 2 (три) — нет.
    scores = {
        1: {RaterRole.SELF: 4.0, RaterRole.PEER: 1.0},
        2: {RaterRole.SELF: 4.0, RaterRole.PEER: 5.0},
    }
    redacted = redact_peer_scores(scores, {1: 2, 2: 3})
    assert RaterRole.PEER not in redacted[1]
    assert redacted[2][RaterRole.PEER] == 5.0


def test_redact_drops_competency_left_empty() -> None:
    # Ответили только пиры, и их мало — от компетенции не остаётся ничего.
    assert redact_peer_scores({1: {RaterRole.PEER: 4.0}}, {1: 1}) == {}


def test_redact_missing_count_means_no_peers() -> None:
    assert redact_peer_scores({1: {RaterRole.PEER: 4.0}}, {}) == {}


# --- overall_by_competency ---


def test_overall_includes_self_with_other_roles() -> None:
    assert overall_by_competency({1: {RaterRole.SELF: 4.0, RaterRole.TEACHER: 2.0}}) == {1: 3.0}


def test_overall_averages_all_present_roles() -> None:
    scores = {1: {RaterRole.SELF: 4.0, RaterRole.PEER: 2.0, RaterRole.TEACHER: 3.0}}
    assert overall_by_competency(scores) == {1: 3.0}


def test_overall_empty_input() -> None:
    assert overall_by_competency({}) == {}


# --- self_by_competency / others_by_competency ---


def test_self_by_competency_extracts_only_self() -> None:
    scores = {1: {RaterRole.SELF: 4.0, RaterRole.TEACHER: 2.0}, 2: {RaterRole.TEACHER: 3.0}}
    assert self_by_competency(scores) == {1: 4.0}


def test_others_excludes_self() -> None:
    scores = {1: {RaterRole.SELF: 5.0, RaterRole.TEACHER: 2.0, RaterRole.PARENT: 4.0}}
    assert others_by_competency(scores) == {1: 3.0}


def test_others_absent_when_only_self_answered() -> None:
    assert others_by_competency({1: {RaterRole.SELF: 5.0}}) == {}


# --- compute_gap ---


def test_compute_gap_present_in_both() -> None:
    assert compute_gap({1: 4.0}, {1: 3.0}) == {1: 1.0}


def test_compute_gap_negative_when_self_lower() -> None:
    assert compute_gap({1: 2.0}, {1: 3.5}) == {1: -1.5}


def test_compute_gap_missing_on_either_side_is_dropped() -> None:
    assert compute_gap({1: 4.0, 2: 3.0}, {1: 3.0}) == {1: 1.0}
    assert compute_gap({1: 4.0}, {1: 3.0, 2: 2.0}) == {1: 1.0}


# --- pick_growth_zones ---


def test_pick_growth_zones_lowest_first() -> None:
    assert pick_growth_zones({1: 4.0, 2: 2.0, 3: 3.0, 4: 5.0}, n=3) == [2, 3, 1]


def test_pick_growth_zones_tie_broken_by_competency_id() -> None:
    assert pick_growth_zones({3: 2.0, 1: 2.0, 2: 2.0}, n=2) == [1, 2]


def test_pick_growth_zones_n_larger_than_available() -> None:
    assert pick_growth_zones({1: 4.0, 2: 2.0}, n=5) == [2, 1]


# --- can_view_results ---


def test_can_view_results_self() -> None:
    assert can_view_results(1, UserRole.STUDENT, 1, set(), set()) is True


def test_can_view_results_admin() -> None:
    assert can_view_results(99, UserRole.ADMIN, 1, set(), set()) is True


def test_can_view_results_teacher_of_class() -> None:
    assert can_view_results(10, UserRole.TEACHER, 1, {10}, set()) is True


def test_can_view_results_parent() -> None:
    assert can_view_results(20, UserRole.PARENT, 1, set(), {20}) is True


def test_can_view_results_unrelated_denied() -> None:
    assert can_view_results(2, UserRole.STUDENT, 1, {10}, {20}) is False


# --- Интеграционные тесты GET /results/{subject_id} ---


@pytest.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


async def _seed_competency(db_session, code: str, order: int) -> int:
    """Компетенция с одним вопросом — среднее считается по единственному
    числу, результат легко проверить руками."""
    area_id = (await db_session.execute(select(OutcomeArea.id))).scalars().first()
    comp = Competency(code=code, name=f"Компетенция {code}", order=order, outcome_area_id=area_id)
    db_session.add(comp)
    await db_session.flush()
    version_id = (
        await db_session.execute(
            select(QuestionnaireVersion.id).where(QuestionnaireVersion.is_current.is_(True))
        )
    ).scalar_one()
    db_session.add(
        Question(
            competency_id=comp.id,
            text="вопрос",
            order=0,
            version_id=version_id,
        )
    )
    await db_session.commit()
    return comp.id


async def _question_id_for(db_session, competency_id: int) -> int:
    row = await db_session.execute(select(Question).where(Question.competency_id == competency_id))
    return row.scalar_one().id


async def _register(client: AsyncClient, email: str, role: str) -> int:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": f"Тест {role}", "role": role},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    login = await client.post("/auth/login", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _answer_as(
    client: AsyncClient,
    db_session,
    email: str,
    respondent_id: int,
    subject_id: int,
    question_id: int,
    value: int,
) -> None:
    row = await db_session.execute(
        select(Assessment.id).where(
            Assessment.respondent_id == respondent_id, Assessment.subject_id == subject_id
        )
    )
    aid = row.scalar_one()
    headers = await _login(client, email)
    response = await client.post(
        f"/assessments/{aid}/answers",
        json={"answers": [{"question_id": question_id, "value": value}]},
        headers=headers,
    )
    assert response.status_code == 200


@pytest.fixture
async def results_scenario(client: AsyncClient, admin_headers: dict[str, str]) -> dict:
    """Класс 10-Р: ученики s1 (субъект) .. s4, учитель t1, родитель p1 → s1.
    Кампания с include_peers=True — про s1 могут ответить и s2/s3/s4.
    """
    s1 = await _register(client, "rs1@vektor.ru", "student")
    s2 = await _register(client, "rs2@vektor.ru", "student")
    s3 = await _register(client, "rs3@vektor.ru", "student")
    s4 = await _register(client, "rs4@vektor.ru", "student")
    t1 = await _register(client, "rt1@vektor.ru", "teacher")
    p1 = await _register(client, "rp1@vektor.ru", "parent")

    cls = (
        await client.post("/classes", json={"grade": 10, "section": "р"}, headers=admin_headers)
    ).json()
    class_id = cls["id"]
    await client.post(
        f"/classes/{class_id}/students",
        json={"student_ids": [s1, s2, s3, s4]},
        headers=admin_headers,
    )
    await client.post(
        f"/classes/{class_id}/teachers", json={"teacher_ids": [t1]}, headers=admin_headers
    )
    await client.post(f"/users/{p1}/children", json={"child_ids": [s1]}, headers=admin_headers)

    campaign = (
        await client.post(
            "/campaigns",
            json={"title": "360 · результаты", "period": "2026-06"},
            headers=admin_headers,
        )
    ).json()
    campaign_id = campaign["id"]
    await client.post(
        f"/campaigns/{campaign_id}/generate",
        json={"class_ids": [class_id], "include_peers": True},
        headers=admin_headers,
    )

    return {
        "campaign_id": campaign_id,
        "class_id": class_id,
        "ids": {"s1": s1, "s2": s2, "s3": s3, "s4": s4, "t1": t1, "p1": p1},
    }


async def test_results_not_found_unknown_campaign(
    client: AsyncClient, admin_headers, results_scenario
) -> None:
    response = await client.get(
        f"/results/{results_scenario['ids']['s1']}?campaign_id=99999", headers=admin_headers
    )
    assert response.status_code == 404


async def test_results_not_found_unknown_subject(
    client: AsyncClient, admin_headers, results_scenario
) -> None:
    response = await client.get(
        f"/results/99999?campaign_id={results_scenario['campaign_id']}", headers=admin_headers
    )
    assert response.status_code == 404


async def test_results_forbidden_for_unrelated_student(
    client: AsyncClient, results_scenario
) -> None:
    s2_headers = await _login(client, "rs2@vektor.ru")
    # s2 не является ни s1, ни учителем, ни родителем s1.
    response = await client.get(
        f"/results/{results_scenario['ids']['s1']}?campaign_id={results_scenario['campaign_id']}",
        headers=s2_headers,
    )
    assert response.status_code == 403


async def test_results_visible_to_self_teacher_parent_and_admin(
    client: AsyncClient, admin_headers, results_scenario
) -> None:
    ids = results_scenario["ids"]
    campaign_id = results_scenario["campaign_id"]

    for email in ["rs1@vektor.ru", "rt1@vektor.ru", "rp1@vektor.ru"]:
        headers = await _login(client, email)
        response = await client.get(
            f"/results/{ids['s1']}?campaign_id={campaign_id}", headers=headers
        )
        assert response.status_code == 200, email

    admin_response = await client.get(
        f"/results/{ids['s1']}?campaign_id={campaign_id}", headers=admin_headers
    )
    assert admin_response.status_code == 200


async def test_results_peer_layer_hidden_below_threshold_then_shown(
    client: AsyncClient, results_scenario, db_session
) -> None:
    ids = results_scenario["ids"]
    campaign_id = results_scenario["campaign_id"]
    comp_id = await _seed_competency(db_session, "R1", 1)
    question_id = await _question_id_for(db_session, comp_id)

    await _answer_as(client, db_session, "rs1@vektor.ru", ids["s1"], ids["s1"], question_id, 4)
    await _answer_as(client, db_session, "rt1@vektor.ru", ids["t1"], ids["s1"], question_id, 3)
    await _answer_as(client, db_session, "rp1@vektor.ru", ids["p1"], ids["s1"], question_id, 5)
    # только 2 пира — ниже порога.
    await _answer_as(client, db_session, "rs2@vektor.ru", ids["s2"], ids["s1"], question_id, 2)
    await _answer_as(client, db_session, "rs3@vektor.ru", ids["s3"], ids["s1"], question_id, 4)

    headers = await _login(client, "rs1@vektor.ru")
    before = (
        await client.get(f"/results/{ids['s1']}?campaign_id={campaign_id}", headers=headers)
    ).json()
    comp_before = next(c for c in before["competencies"] if c["competency_id"] == comp_id)
    assert before["any_peer_scores_disclosed"] is False
    assert comp_before["peer_scores_disclosed"] is False
    assert comp_before["peer_avg"] is None  # скрыт, хотя данные формально есть
    assert comp_before["self_avg"] == 4.0
    assert comp_before["overall_avg"] == pytest.approx((4 + 3 + 5) / 3)  # PEER не участвует
    assert comp_before["others_avg"] == pytest.approx((3 + 5) / 2)
    assert comp_before["gap"] == pytest.approx(4 - (3 + 5) / 2)

    # третий пир отвечает — порог достигнут.
    await _answer_as(client, db_session, "rs4@vektor.ru", ids["s4"], ids["s1"], question_id, 3)

    after = (
        await client.get(f"/results/{ids['s1']}?campaign_id={campaign_id}", headers=headers)
    ).json()
    comp_after = next(c for c in after["competencies"] if c["competency_id"] == comp_id)
    assert after["any_peer_scores_disclosed"] is True
    assert comp_after["peer_scores_disclosed"] is True
    assert comp_after["peer_rater_count"] == 3
    assert comp_after["peer_avg"] == pytest.approx((2 + 4 + 3) / 3)
    assert comp_after["overall_avg"] == pytest.approx((4 + 3 + 5 + (2 + 4 + 3) / 3) / 4)


async def test_partial_peer_answers_do_not_expose_single_author(
    client: AsyncClient, results_scenario, db_session
) -> None:
    """РЕГРЕССИЯ: порог считается по компетенции, а не «ответил хоть что-то».

    Анкеты заполняются частями, поэтому три разных пира могут ответить на
    РАЗНЫЕ компетенции. Раньше глобальный счётчик показывал 3 и раскрывал
    компетенцию, где ответил ровно один человек.
    """
    ids = results_scenario["ids"]
    campaign_id = results_scenario["campaign_id"]
    comp_a = await _seed_competency(db_session, "A", 1)
    comp_b = await _seed_competency(db_session, "B", 2)
    qa = await _question_id_for(db_session, comp_a)
    qb = await _question_id_for(db_session, comp_b)

    # Компетенцию A оценил ТОЛЬКО s2; компетенцию B — s3 и s4.
    # Всего ответивших пиров 3 — глобальный порог формально «пройден».
    await _answer_as(client, db_session, "rs2@vektor.ru", ids["s2"], ids["s1"], qa, 1)
    await _answer_as(client, db_session, "rs3@vektor.ru", ids["s3"], ids["s1"], qb, 5)
    await _answer_as(client, db_session, "rs4@vektor.ru", ids["s4"], ids["s1"], qb, 5)

    headers = await _login(client, "rs1@vektor.ru")
    body = (
        await client.get(f"/results/{ids['s1']}?campaign_id={campaign_id}", headers=headers)
    ).json()

    a = next(c for c in body["competencies"] if c["competency_id"] == comp_a)
    b = next(c for c in body["competencies"] if c["competency_id"] == comp_b)
    # A: один автор — раскрывать нельзя ни при каких обстоятельствах.
    assert a["peer_avg"] is None
    assert a["peer_scores_disclosed"] is False
    assert a["overall_avg"] is None  # других ролей нет, компетенция выпала
    # B: два автора — тоже ниже порога.
    assert b["peer_avg"] is None


async def test_rater_role_survives_class_transfer(
    client: AsyncClient, admin_headers, results_scenario, db_session
) -> None:
    """РЕГРЕССИЯ: роль фиксируется при генерации, а не выводится при чтении.

    Перевод ученика в следующий класс — штатное ежегодное событие. Раньше
    после него учитель прошлого года превращался в «одноклассника»: его
    оценка исчезала из слоя teacher и попадала в пул анонимности peer.
    """
    ids = results_scenario["ids"]
    campaign_id = results_scenario["campaign_id"]
    comp_id = await _seed_competency(db_session, "T1", 1)
    question_id = await _question_id_for(db_session, comp_id)

    await _answer_as(client, db_session, "rt1@vektor.ru", ids["t1"], ids["s1"], question_id, 5)

    headers = await _login(client, "rs1@vektor.ru")
    before = (
        await client.get(f"/results/{ids['s1']}?campaign_id={campaign_id}", headers=headers)
    ).json()
    comp_before = next(c for c in before["competencies"] if c["competency_id"] == comp_id)
    assert comp_before["teacher_avg"] == 5.0
    assert comp_before["peer_rater_count"] == 0

    # НОВЫЙ УЧЕБНЫЙ ГОД: админ переводит ученика в 11-й класс.
    new_class = (
        await client.post("/classes", json={"grade": 11, "section": "н"}, headers=admin_headers)
    ).json()
    await client.post(
        f"/classes/{new_class['id']}/students",
        json={"student_ids": [ids["s1"]]},
        headers=admin_headers,
    )

    after = (
        await client.get(f"/results/{ids['s1']}?campaign_id={campaign_id}", headers=admin_headers)
    ).json()
    comp_after = next(c for c in after["competencies"] if c["competency_id"] == comp_id)
    # Прошлые результаты не переписаны: учитель остался учителем.
    assert comp_after["teacher_avg"] == 5.0
    assert comp_after["peer_rater_count"] == 0


async def test_results_growth_zones_lowest_first(
    client: AsyncClient, results_scenario, db_session
) -> None:
    ids = results_scenario["ids"]
    campaign_id = results_scenario["campaign_id"]
    strong_id = await _seed_competency(db_session, "STRONG", 1)
    weak_id = await _seed_competency(db_session, "WEAK", 2)
    strong_question_id = await _question_id_for(db_session, strong_id)
    weak_question_id = await _question_id_for(db_session, weak_id)

    await _answer_as(
        client, db_session, "rs1@vektor.ru", ids["s1"], ids["s1"], strong_question_id, 5
    )
    await _answer_as(client, db_session, "rs1@vektor.ru", ids["s1"], ids["s1"], weak_question_id, 2)

    headers = await _login(client, "rs1@vektor.ru")
    body = (
        await client.get(f"/results/{ids['s1']}?campaign_id={campaign_id}", headers=headers)
    ).json()

    growth_zone_ids = [z["competency_id"] for z in body["growth_zones"]]
    assert growth_zone_ids[0] == weak_id
    assert strong_id in growth_zone_ids  # только 2 компетенции с данными — обе войдут


async def test_gap_reflects_self_versus_others(
    client: AsyncClient, results_scenario, db_session
) -> None:
    ids = results_scenario["ids"]
    campaign_id = results_scenario["campaign_id"]
    comp_id = await _seed_competency(db_session, "G1", 1)
    question_id = await _question_id_for(db_session, comp_id)

    # себя — на 5, учитель и родитель — на 2 и 3 (среднее других 2.5).
    await _answer_as(client, db_session, "rs1@vektor.ru", ids["s1"], ids["s1"], question_id, 5)
    await _answer_as(client, db_session, "rt1@vektor.ru", ids["t1"], ids["s1"], question_id, 2)
    await _answer_as(client, db_session, "rp1@vektor.ru", ids["p1"], ids["s1"], question_id, 3)

    headers = await _login(client, "rs1@vektor.ru")
    body = (
        await client.get(f"/results/{ids['s1']}?campaign_id={campaign_id}", headers=headers)
    ).json()
    comp = next(c for c in body["competencies"] if c["competency_id"] == comp_id)

    assert comp["others_avg"] == pytest.approx(2.5)
    assert comp["gap"] == pytest.approx(2.5)  # себя оценивает выше на 2.5
