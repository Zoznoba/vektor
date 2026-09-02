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
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import async_sessionmaker

from vektor.modules.assessments.models import Assessment, Campaign
from vektor.modules.competencies.models import (
    Competency,
    OutcomeArea,
    Question,
    QuestionnaireVersion,
)
from vektor.modules.results.service import (
    ScoredAnswer,
    aggregate_by_competency_and_rater,
    average_profiles,
    can_disclose_peer_scores,
    can_view_class_results,
    can_view_results,
    compute_deltas,
    compute_gap,
    core_average,
    count_growth_zone_hits,
    count_peer_raters_by_competency,
    others_by_competency,
    overall_by_competency,
    overall_scores_from_answers,
    pick_growth_zones,
    rank_growth_zones_by_hits,
    redact_peer_scores,
    self_by_competency,
    shared_competencies,
)
from vektor.shared.enums import CampaignStatus, RaterRole, UserRole


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


# --- can_view_class_results (5e) ---


def test_can_view_class_results_admin() -> None:
    assert can_view_class_results(1, UserRole.ADMIN, set()) is True


def test_can_view_class_results_teacher_of_class() -> None:
    assert can_view_class_results(10, UserRole.TEACHER, {10, 11}) is True


def test_can_view_class_results_other_teacher_denied() -> None:
    # Учитель ЧУЖОГО класса класс целиком не видит.
    assert can_view_class_results(12, UserRole.TEACHER, {10, 11}) is False


def test_can_view_class_results_parent_and_student_denied() -> None:
    assert can_view_class_results(20, UserRole.PARENT, {10}) is False
    assert can_view_class_results(1, UserRole.STUDENT, {10}) is False


# --- overall_scores_from_answers: цепочка целиком ---


def test_overall_scores_from_answers_applies_redaction() -> None:
    # Два пира — ниже порога, слой PEER обязан исчезнуть ещё внутри цепочки,
    # иначе он «протечёт» в динамику и в средний профиль класса.
    answers = [
        ScoredAnswer(competency_id=1, rater_role=RaterRole.SELF, respondent_id=1, value=5),
        _peer(1, 2, 1),
        _peer(1, 3, 1),
    ]
    assert overall_scores_from_answers(answers) == {1: 5.0}


def test_overall_scores_from_answers_keeps_peer_at_threshold() -> None:
    answers = [
        ScoredAnswer(competency_id=1, rater_role=RaterRole.SELF, respondent_id=1, value=5),
        _peer(1, 2, 1),
        _peer(1, 3, 1),
        _peer(1, 4, 1),
    ]
    # self=5, peer=(1+1+1)/3=1 → среднее по ролям = 3.0
    assert overall_scores_from_answers(answers) == {1: 3.0}


# --- 5d: shared_competencies / compute_deltas / core_average ---


def test_shared_competencies_is_intersection() -> None:
    assert shared_competencies({1: 3.0, 2: 4.0}, {2: 3.5, 3: 2.0}) == {2}


def test_shared_competencies_empty_when_no_previous() -> None:
    assert shared_competencies({1: 3.0}, {}) == set()


def test_compute_deltas_only_over_core() -> None:
    current = {1: 4.0, 2: 5.0}
    previous = {1: 3.0, 3: 2.0}
    # Ядро — только критерий 1. У 2 нет прошлого, у 3 нет текущего.
    assert compute_deltas(current, previous, {1}) == {1: 1.0}


def test_compute_deltas_negative_when_dropped() -> None:
    assert compute_deltas({1: 2.5}, {1: 3.0}, {1}) == {1: -0.5}


def test_compute_deltas_ignores_competency_outside_core() -> None:
    # Критерий появился в этом году: значение есть, дельты быть не должно —
    # иначе нарисуем прирост, которого не было.
    current = {1: 4.0, 9: 3.0}
    previous = {1: 4.0}
    assert 9 not in compute_deltas(current, previous, shared_competencies(current, previous))


def test_core_average_uses_only_core() -> None:
    # Критерий 2 в ядро не входит и на итог влиять не должен.
    assert core_average({1: 3.0, 2: 5.0}, {1}) == 3.0


def test_core_average_none_when_core_empty() -> None:
    assert core_average({1: 3.0}, set()) is None


def test_core_average_ignores_missing_competency() -> None:
    assert core_average({1: 4.0}, {1, 42}) == 4.0


# --- 5e: average_profiles / count_growth_zone_hits / rank_growth_zones_by_hits ---


def test_average_profiles_weighs_students_equally() -> None:
    # Каждый ученик — один голос, независимо от числа оценивших его людей.
    assert average_profiles([{1: 2.0}, {1: 4.0}]) == {1: 3.0}


def test_average_profiles_handles_partial_competencies() -> None:
    # Критерий 2 есть только у одного ученика — усредняем по тем, у кого он есть.
    assert average_profiles([{1: 2.0, 2: 5.0}, {1: 4.0}]) == {1: 3.0, 2: 5.0}


def test_average_profiles_empty() -> None:
    assert average_profiles([]) == {}


def test_count_growth_zone_hits() -> None:
    assert count_growth_zone_hits([[1, 2], [2, 3], [2]]) == {1: 1, 2: 3, 3: 1}


def test_rank_growth_zones_by_coverage_not_by_score() -> None:
    # 5 учеников против 2 — первым идёт более массовый критерий.
    assert rank_growth_zones_by_hits({1: 2, 2: 5}, n=2) == [2, 1]


def test_rank_growth_zones_tie_broken_by_competency_id() -> None:
    assert rank_growth_zones_by_hits({3: 2, 1: 2, 2: 2}, n=2) == [1, 2]


def test_rank_growth_zones_n_larger_than_available() -> None:
    assert rank_growth_zones_by_hits({1: 1}, n=5) == [1]


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


async def _set_campaign_status(db_session, campaign_id: int, status: CampaignStatus) -> None:
    await db_session.execute(
        sa_update(Campaign).where(Campaign.id == campaign_id).values(status=status)
    )
    await db_session.commit()


async def _post_answer(
    client: AsyncClient, db_session, email: str, assessment_id: int, question_id: int, value: int
) -> None:
    """Подать ответ и оставить кампанию ЗАВЕРШЁННОЙ.

    Два правила системы смотрят в разные стороны: ответы принимаются только в
    активную кампанию (submit_answers), а результаты считаются только по
    завершённой (_load_completed_campaign). Поэтому в тестах ответ подаётся в
    активную, а сразу после кампания закрывается: дальше тест читает
    результаты так же, как их читают в жизни — после закрытия диагностики.
    """
    campaign_id = await db_session.scalar(
        select(Assessment.campaign_id).where(Assessment.id == assessment_id)
    )
    await _set_campaign_status(db_session, campaign_id, CampaignStatus.ACTIVE)
    headers = await _login(client, email)
    response = await client.post(
        f"/assessments/{assessment_id}/answers",
        json={"answers": [{"question_id": question_id, "value": value}]},
        headers=headers,
    )
    assert response.status_code == 200
    await _set_campaign_status(db_session, campaign_id, CampaignStatus.CLOSED)


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
    await _post_answer(client, db_session, email, aid, question_id, value)


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
            json={"title": "360 · результаты", "period_year": 2026, "period_month": 6},
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
    client: AsyncClient, admin_headers, results_scenario, db_session
) -> None:
    ids = results_scenario["ids"]
    campaign_id = results_scenario["campaign_id"]
    # Ответов в этом тесте нет (проверяются только права), поэтому кампанию
    # закрываем руками: по незавершённой результаты не отдаются вовсе.
    await _set_campaign_status(db_session, campaign_id, CampaignStatus.CLOSED)

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


async def test_results_rejected_while_campaign_is_not_completed(
    client: AsyncClient, admin_headers, results_scenario, db_session
) -> None:
    """Результаты считаются только по ЗАВЕРШЁННОЙ кампании.

    Пока диагностика идёт, агрегаты меняются с каждым пришедшим ответом:
    критерий с двумя ответами уезжает в зоны роста, слой одноклассников то
    раскрывается, то снова прячется по порогу. Показывать это как «результат»
    нельзя, поэтому 409, а не половинчатые цифры.
    """
    ids = results_scenario["ids"]
    campaign_id = results_scenario["campaign_id"]

    for status_value in (CampaignStatus.DRAFT, CampaignStatus.ACTIVE):
        await _set_campaign_status(db_session, campaign_id, status_value)
        response = await client.get(
            f"/results/{ids['s1']}?campaign_id={campaign_id}", headers=admin_headers
        )
        assert response.status_code == 409, status_value
        assert response.json()["code"] == "campaign_not_completed"

    await _set_campaign_status(db_session, campaign_id, CampaignStatus.CLOSED)
    ok = await client.get(f"/results/{ids['s1']}?campaign_id={campaign_id}", headers=admin_headers)
    assert ok.status_code == 200


async def test_results_ignore_unfinished_campaign_when_resolving_latest(
    client: AsyncClient, admin_headers, results_scenario, db_session
) -> None:
    """РЕГРЕССИЯ (находка 7g): пустая кампания-артефакт с более поздним
    периодом подменяла собой реальные результаты. Незавершённая кампания в
    резолюцию «последней» больше не попадает вовсе."""
    ids = results_scenario["ids"]
    comp_id = await _seed_competency(db_session, "LATEST", 1)
    question_id = await _question_id_for(db_session, comp_id)
    await _answer_as(client, db_session, "rs1@vektor.ru", ids["s1"], ids["s1"], question_id, 4)

    artifact = (
        await client.post(
            "/campaigns",
            json={"title": "E2E UI check", "period_year": 2026, "period_month": 9},
            headers=admin_headers,
        )
    ).json()
    await client.post(
        f"/campaigns/{artifact['id']}/generate",
        json={"class_ids": [results_scenario["class_id"]]},
        headers=admin_headers,
    )

    body = (await client.get(f"/results/{ids['s1']}", headers=admin_headers)).json()
    assert body["campaign_id"] == results_scenario["campaign_id"]

    campaigns = (await client.get(f"/results/{ids['s1']}/campaigns", headers=admin_headers)).json()
    assert [c["campaign_id"] for c in campaigns] == [results_scenario["campaign_id"]]


# --- Срез 5d: динамика между периодами (GET /results/{id}/dynamics) ---


async def _answer_in_campaign(
    client: AsyncClient,
    db_session,
    email: str,
    respondent_id: int,
    subject_id: int,
    campaign_id: int,
    question_id: int,
    value: int,
) -> None:
    """Как _answer_as, но с фильтром по кампании: в сценариях с двумя периодами
    у одной пары респондент/субъект анкет несколько."""
    row = await db_session.execute(
        select(Assessment.id).where(
            Assessment.respondent_id == respondent_id,
            Assessment.subject_id == subject_id,
            Assessment.campaign_id == campaign_id,
        )
    )
    aid = row.scalar_one()
    await _post_answer(client, db_session, email, aid, question_id, value)


@pytest.fixture
async def dynamics_scenario(client: AsyncClient, admin_headers: dict[str, str], db_session) -> dict:
    """Два периода подряд у одного ученика.

    Критерий A отвечен в ОБА года (попадёт в общее ядро), критерий B — только
    во второй: так воспроизводится «критерий появился», для которого дельты
    быть не должно.
    """
    s1 = await _register(client, "ds1@vektor.ru", "student")
    t1 = await _register(client, "dt1@vektor.ru", "teacher")

    cls = (
        await client.post("/classes", json={"grade": 9, "section": "д"}, headers=admin_headers)
    ).json()
    class_id = cls["id"]
    await client.post(
        f"/classes/{class_id}/students", json={"student_ids": [s1]}, headers=admin_headers
    )
    await client.post(
        f"/classes/{class_id}/teachers", json={"teacher_ids": [t1]}, headers=admin_headers
    )

    comp_a = await _seed_competency(db_session, "dyn_a", order=1)
    comp_b = await _seed_competency(db_session, "dyn_b", order=2)
    q_a = await _question_id_for(db_session, comp_a)
    q_b = await _question_id_for(db_session, comp_b)

    campaigns = {}
    for period in (2025, 2026):
        campaign = (
            await client.post(
                "/campaigns",
                json={"title": f"360 · {period}", "period_year": period, "period_month": 6},
                headers=admin_headers,
            )
        ).json()
        await client.post(
            f"/campaigns/{campaign['id']}/generate",
            json={"class_ids": [class_id]},
            headers=admin_headers,
        )
        campaigns[period] = campaign["id"]

    # 2025: только критерий A (self=3, teacher=3 → overall 3.0)
    await _answer_in_campaign(client, db_session, "ds1@vektor.ru", s1, s1, campaigns[2025], q_a, 3)
    await _answer_in_campaign(client, db_session, "dt1@vektor.ru", t1, s1, campaigns[2025], q_a, 3)
    # 2026: A вырос до 4.0, плюс появился B
    await _answer_in_campaign(client, db_session, "ds1@vektor.ru", s1, s1, campaigns[2026], q_a, 4)
    await _answer_in_campaign(client, db_session, "dt1@vektor.ru", t1, s1, campaigns[2026], q_a, 4)
    await _answer_in_campaign(client, db_session, "ds1@vektor.ru", s1, s1, campaigns[2026], q_b, 5)

    return {
        "class_id": class_id,
        "campaigns": campaigns,
        "comp_a": comp_a,
        "comp_b": comp_b,
        "ids": {"s1": s1, "t1": t1},
    }


async def test_dynamics_compares_with_previous_period(
    client: AsyncClient, dynamics_scenario
) -> None:
    s1 = dynamics_scenario["ids"]["s1"]
    headers = await _login(client, "ds1@vektor.ru")
    body = (await client.get(f"/results/{s1}/dynamics", headers=headers)).json()

    assert body["campaign_period_year"] == 2026
    assert body["previous_campaign_period_year"] == 2025
    assert body["previous_campaign_id"] == dynamics_scenario["campaigns"][2025]

    comp_a = next(
        c for c in body["competencies"] if c["competency_id"] == dynamics_scenario["comp_a"]
    )
    assert comp_a["in_core"] is True
    assert comp_a["overall_avg"] == pytest.approx(4.0)
    assert comp_a["previous_avg"] == pytest.approx(3.0)
    assert comp_a["delta"] == pytest.approx(1.0)


async def test_dynamics_appeared_competency_has_value_but_no_delta(
    client: AsyncClient, dynamics_scenario
) -> None:
    # Критерий B появился только во втором периоде: значение показываем,
    # дельту — нет, иначе нарисуем прирост с нуля.
    s1 = dynamics_scenario["ids"]["s1"]
    headers = await _login(client, "ds1@vektor.ru")
    body = (await client.get(f"/results/{s1}/dynamics", headers=headers)).json()

    comp_b = next(
        c for c in body["competencies"] if c["competency_id"] == dynamics_scenario["comp_b"]
    )
    assert comp_b["in_core"] is False
    assert comp_b["overall_avg"] == pytest.approx(5.0)
    assert comp_b["previous_avg"] is None
    assert comp_b["delta"] is None


async def test_dynamics_core_average_ignores_appeared_competency(
    client: AsyncClient, dynamics_scenario
) -> None:
    # Ядро — только A. Если бы в итог попал появившийся B (5.0), среднее
    # выросло бы само по себе, без роста ученика.
    s1 = dynamics_scenario["ids"]["s1"]
    headers = await _login(client, "ds1@vektor.ru")
    body = (await client.get(f"/results/{s1}/dynamics", headers=headers)).json()

    assert body["core_competencies_count"] == 1
    assert body["core_average"] == pytest.approx(4.0)
    assert body["previous_core_average"] == pytest.approx(3.0)
    assert body["core_average_delta"] == pytest.approx(1.0)


async def test_dynamics_without_previous_period_is_not_404(
    client: AsyncClient, dynamics_scenario
) -> None:
    # У первого года обучения прошлого периода нет — это штатное состояние.
    s1 = dynamics_scenario["ids"]["s1"]
    headers = await _login(client, "ds1@vektor.ru")
    first = dynamics_scenario["campaigns"][2025]

    response = await client.get(f"/results/{s1}/dynamics?campaign_id={first}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["previous_campaign_id"] is None
    assert body["core_average_delta"] is None
    # Текущие баллы при этом на месте.
    comp_a = next(
        c for c in body["competencies"] if c["competency_id"] == dynamics_scenario["comp_a"]
    )
    assert comp_a["overall_avg"] == pytest.approx(3.0)


async def test_dynamics_orders_periods_by_month_within_year(
    client: AsyncClient, admin_headers, dynamics_scenario, db_session
) -> None:
    # РЕГРЕССИЯ на прод-баг, который жил, пока период был свободной строкой:
    # "2026" — префикс "2026-02" и потому лексикографически МЕНЬШЕ, так что
    # хронологию приходилось восстанавливать разбором ярлыка (period_sort_key
    # с месяцем-заглушкой 13). С числовыми год/месяц порядок обычный, и
    # сентябрь того же года честно оказывается ПОЗЖЕ июня.
    s1 = dynamics_scenario["ids"]["s1"]
    september = (
        await client.post(
            "/campaigns",
            json={"title": "360 · сентябрь 2026", "period_year": 2026, "period_month": 9},
            headers=admin_headers,
        )
    ).json()
    await client.post(
        f"/campaigns/{september['id']}/generate",
        json={"class_ids": [dynamics_scenario["class_id"]]},
        headers=admin_headers,
    )
    q_a = await _question_id_for(db_session, dynamics_scenario["comp_a"])
    await _answer_in_campaign(client, db_session, "ds1@vektor.ru", s1, s1, september["id"], q_a, 5)

    headers = await _login(client, "ds1@vektor.ru")

    # Без campaign_id берётся САМАЯ СВЕЖАЯ — сентябрьская, а не июньская.
    latest = (await client.get(f"/results/{s1}/dynamics", headers=headers)).json()
    assert latest["campaign_id"] == september["id"]
    # Предыдущей для неё оказывается июнь ТОГО ЖЕ года, а не прошлогодняя.
    assert latest["previous_campaign_id"] == dynamics_scenario["campaigns"][2026]
    assert latest["previous_campaign_period_year"] == 2026
    assert latest["previous_campaign_period_month"] == 6


async def test_dynamics_same_period_campaign_is_not_previous(
    client: AsyncClient, admin_headers, dynamics_scenario, db_session
) -> None:
    # Вторая кампания ТОГО ЖЕ периода не является предыдущей: сравнение идёт
    # строго по периодам, иначе два класса одного года стали бы «динамикой».
    s1 = dynamics_scenario["ids"]["s1"]
    twin = (
        await client.post(
            "/campaigns",
            json={"title": "360 · 2026 второй", "period_year": 2026, "period_month": 6},
            headers=admin_headers,
        )
    ).json()
    await client.post(
        f"/campaigns/{twin['id']}/generate",
        json={"class_ids": [dynamics_scenario["class_id"]]},
        headers=admin_headers,
    )
    q_a = await _question_id_for(db_session, dynamics_scenario["comp_a"])
    await _answer_in_campaign(client, db_session, "ds1@vektor.ru", s1, s1, twin["id"], q_a, 2)

    headers = await _login(client, "ds1@vektor.ru")
    body = (
        await client.get(f"/results/{s1}/dynamics?campaign_id={twin['id']}", headers=headers)
    ).json()

    assert body["previous_campaign_period_year"] == 2025


async def test_dynamics_reports_version_change(
    client: AsyncClient, dynamics_scenario, db_session
) -> None:
    # Архивной кампании подменяем редакцию анкеты — фронт должен получить
    # признак и текст оговорки ИЗ САМОЙ редакции, а не выдуманный.
    archive = QuestionnaireVersion(
        code="archive-test",
        title="Архивная редакция",
        note="Формулировки отличаются, сравнение приблизительное.",
        is_current=False,
    )
    db_session.add(archive)
    await db_session.flush()
    await db_session.execute(
        sa_update(Campaign)
        .where(Campaign.id == dynamics_scenario["campaigns"][2025])
        .values(questionnaire_version_id=archive.id)
    )
    await db_session.commit()

    s1 = dynamics_scenario["ids"]["s1"]
    headers = await _login(client, "ds1@vektor.ru")
    body = (await client.get(f"/results/{s1}/dynamics", headers=headers)).json()

    assert body["versions_differ"] is True
    assert body["version_note"] == "Формулировки отличаются, сравнение приблизительное."


async def test_dynamics_forbidden_for_unrelated_student(
    client: AsyncClient, dynamics_scenario
) -> None:
    outsider = await _register(client, "dout@vektor.ru", "student")
    assert outsider  # зарегистрировался, но к классу отношения не имеет
    headers = await _login(client, "dout@vektor.ru")
    response = await client.get(
        f"/results/{dynamics_scenario['ids']['s1']}/dynamics", headers=headers
    )
    assert response.status_code == 403


async def test_subject_campaigns_lists_both_periods(client: AsyncClient, dynamics_scenario) -> None:
    s1 = dynamics_scenario["ids"]["s1"]
    headers = await _login(client, "ds1@vektor.ru")
    body = (await client.get(f"/results/{s1}/campaigns", headers=headers)).json()

    # Свежий период первым — переключатель периодов открывается на актуальном.
    assert [c["period_year"] for c in body] == [2026, 2025]


async def test_subject_campaigns_forbidden_for_unrelated(
    client: AsyncClient, dynamics_scenario
) -> None:
    await _register(client, "dout2@vektor.ru", "student")
    headers = await _login(client, "dout2@vektor.ru")
    response = await client.get(
        f"/results/{dynamics_scenario['ids']['s1']}/campaigns", headers=headers
    )
    assert response.status_code == 403


# --- Срез 5e: агрегаты класса и покрытие кампании ---


@pytest.fixture
async def class_scenario(client: AsyncClient, admin_headers: dict[str, str], db_session) -> dict:
    """Класс 7-К: s1 и s2 с РАЗНЫМ числом оценивших.

    s1 оценивают трое (self + учитель + родитель), s2 — только он сам. Это
    ключевой момент для проверки «каждый ученик весит одинаково»: при
    взвешивании по ответам s1 перетянул бы средний профиль на себя.
    """
    s1 = await _register(client, "cs1@vektor.ru", "student")
    s2 = await _register(client, "cs2@vektor.ru", "student")
    t1 = await _register(client, "ct1@vektor.ru", "teacher")
    p1 = await _register(client, "cp1@vektor.ru", "parent")

    cls = (
        await client.post("/classes", json={"grade": 7, "section": "к"}, headers=admin_headers)
    ).json()
    class_id = cls["id"]
    await client.post(
        f"/classes/{class_id}/students", json={"student_ids": [s1, s2]}, headers=admin_headers
    )
    await client.post(
        f"/classes/{class_id}/teachers", json={"teacher_ids": [t1]}, headers=admin_headers
    )
    await client.post(f"/users/{p1}/children", json={"child_ids": [s1]}, headers=admin_headers)

    comp_a = await _seed_competency(db_session, "cls_a", order=1)
    comp_b = await _seed_competency(db_session, "cls_b", order=2)
    q_a = await _question_id_for(db_session, comp_a)
    q_b = await _question_id_for(db_session, comp_b)

    campaign = (
        await client.post(
            "/campaigns",
            json={"title": "360 · класс", "period_year": 2026, "period_month": 6},
            headers=admin_headers,
        )
    ).json()
    campaign_id = campaign["id"]
    await client.post(
        f"/campaigns/{campaign_id}/generate",
        json={"class_ids": [class_id]},
        headers=admin_headers,
    )

    # s1: критерий A оценён тремя людьми (все ставят 2 → overall 2.0),
    #     критерий B — только собой (5.0).
    for email, rid in (("cs1@vektor.ru", s1), ("ct1@vektor.ru", t1), ("cp1@vektor.ru", p1)):
        await _answer_in_campaign(client, db_session, email, rid, s1, campaign_id, q_a, 2)
    await _answer_in_campaign(client, db_session, "cs1@vektor.ru", s1, s1, campaign_id, q_b, 5)

    # s2: оба критерия только самооценка — A=4.0, B=5.0.
    await _answer_in_campaign(client, db_session, "cs2@vektor.ru", s2, s2, campaign_id, q_a, 4)
    await _answer_in_campaign(client, db_session, "cs2@vektor.ru", s2, s2, campaign_id, q_b, 5)

    return {
        "class_id": class_id,
        "campaign_id": campaign_id,
        "comp_a": comp_a,
        "comp_b": comp_b,
        "ids": {"s1": s1, "s2": s2, "t1": t1, "p1": p1},
    }


async def test_class_results_visible_to_teacher_of_class(
    client: AsyncClient, class_scenario
) -> None:
    headers = await _login(client, "ct1@vektor.ru")
    response = await client.get(f"/results/class/{class_scenario['class_id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["class_label"] == "7-к"


async def test_class_results_visible_to_admin(
    client: AsyncClient, admin_headers, class_scenario
) -> None:
    response = await client.get(
        f"/results/class/{class_scenario['class_id']}", headers=admin_headers
    )
    assert response.status_code == 200


async def test_class_results_forbidden_for_student_and_parent(
    client: AsyncClient, class_scenario
) -> None:
    # Класс целиком не показываем ни ученику, ни родителю — в прототипе этот
    # экран есть только у учителя и админа.
    for email in ("cs1@vektor.ru", "cp1@vektor.ru"):
        headers = await _login(client, email)
        response = await client.get(f"/results/class/{class_scenario['class_id']}", headers=headers)
        assert response.status_code == 403, email


async def test_class_results_unknown_class_404(client: AsyncClient, admin_headers) -> None:
    response = await client.get("/results/class/99999", headers=admin_headers)
    assert response.status_code == 404


async def test_class_profile_weighs_students_equally(
    client: AsyncClient, admin_headers, class_scenario
) -> None:
    # s1 по критерию A = 2.0 (его оценили трое), s2 = 4.0 (только сам).
    # Правильное среднее по КЛАССУ = (2.0 + 4.0) / 2 = 3.0. Если бы считали
    # по ответам, три двойки s1 перевесили бы одну четвёрку s2 → 2.5.
    response = await client.get(
        f"/results/class/{class_scenario['class_id']}", headers=admin_headers
    )
    body = response.json()
    comp_a = next(c for c in body["competencies"] if c["competency_id"] == class_scenario["comp_a"])
    assert comp_a["class_avg"] == pytest.approx(3.0)
    assert body["students_with_results"] == 2


async def test_class_growth_zones_ranked_by_coverage(
    client: AsyncClient, admin_headers, class_scenario
) -> None:
    # Критерий A в личных зонах роста у ОБОИХ учеников (у каждого он ниже B),
    # значит он идёт первым — по охвату.
    response = await client.get(
        f"/results/class/{class_scenario['class_id']}", headers=admin_headers
    )
    zones = response.json()["growth_zones"]
    assert zones[0]["competency_id"] == class_scenario["comp_a"]
    assert zones[0]["students_affected"] == 2


async def test_coverage_requires_admin(client: AsyncClient, class_scenario) -> None:
    # Покрытие по всей школе — админский экран, учителю своего класса не даём.
    headers = await _login(client, "ct1@vektor.ru")
    response = await client.get(
        f"/results/campaigns/{class_scenario['campaign_id']}/coverage", headers=headers
    )
    assert response.status_code == 403


async def test_coverage_counts_by_class_snapshot(
    client: AsyncClient, admin_headers, class_scenario
) -> None:
    response = await client.get(
        f"/results/campaigns/{class_scenario['campaign_id']}/coverage", headers=admin_headers
    )
    assert response.status_code == 200
    body = response.json()
    row = next(c for c in body["groups"] if c["class_id"] == class_scenario["class_id"])
    # Матрица без пиров: self(s1,s2)=2 + teacher(t1→s1,s2)=2 + parent(p1→s1)=1 = 5.
    assert row["total"] == 5
    assert body["total"] == 5


async def test_coverage_keeps_assessments_without_class_snapshot(
    client: AsyncClient, admin_headers, class_scenario, db_session
) -> None:
    # Анкета без снапшота класса (субъект вне класса, пилот на учителях) должна
    # попасть в отдельную строку, а не потеряться: иначе итог по классам
    # перестанет сходиться с общим числом анкет.
    await db_session.execute(
        sa_update(Assessment)
        .where(
            Assessment.campaign_id == class_scenario["campaign_id"],
            Assessment.subject_id == class_scenario["ids"]["s2"],
        )
        .values(subject_class_id=None)
    )
    await db_session.commit()

    body = (
        await client.get(
            f"/results/campaigns/{class_scenario['campaign_id']}/coverage", headers=admin_headers
        )
    ).json()

    orphan = next(c for c in body["groups"] if c["class_id"] is None)
    assert orphan["class_label"] is None
    assert orphan["total"] == 2  # self(s2) + teacher(t1→s2)
    assert sum(c["total"] for c in body["groups"]) == body["total"] == 5


async def test_coverage_unknown_campaign_404(client: AsyncClient, admin_headers) -> None:
    response = await client.get("/results/campaigns/99999/coverage", headers=admin_headers)
    assert response.status_code == 404


def _student_row(body: dict, class_id: int | None, subject_id: int) -> dict:
    row = next(c for c in body["groups"] if c["class_id"] == class_id)
    return next(st for st in row["students"] if st["subject"]["id"] == subject_id)


def _counts(layer: dict) -> dict:
    """Только счётчики слоя: поимённый состав (raters) проверяется отдельно,
    а сравнивать весь словарь целиком в каждом тесте — значит переписывать их
    все при любом новом поле."""
    return {"total": layer["total"], "completed": layer["completed"]}


async def test_coverage_details_students_by_layer(
    client: AsyncClient, admin_headers, class_scenario
) -> None:
    """Детализация покрытия: по каждому ученику — самооценка и слои раторов.

    В фикстуре s1 оценивают трое (сам, учитель, родитель), s2 — только сам
    плюс выданная, но не начатая анкета учителя.
    """
    body = (
        await client.get(
            f"/results/campaigns/{class_scenario['campaign_id']}/coverage", headers=admin_headers
        )
    ).json()
    ids = class_scenario["ids"]

    s1 = _student_row(body, class_scenario["class_id"], ids["s1"])
    assert s1["self_status"] == "completed"
    # Учитель и родитель ответили на один вопрос из двух — анкета выдана и
    # начата, но не завершена.
    assert _counts(s1["teachers"]) == {"total": 1, "completed": 0}
    assert _counts(s1["parents"]) == {"total": 1, "completed": 0}
    # Пиров не генерировали, и своя анкета в слои не попала — иначе учителей
    # оказалось бы двое.
    assert _counts(s1["peers"]) == {"total": 0, "completed": 0}

    s2 = _student_row(body, class_scenario["class_id"], ids["s2"])
    assert s2["self_status"] == "completed"
    assert _counts(s2["teachers"]) == {"total": 1, "completed": 0}
    # Родителя у s2 нет вовсе — это «слой не выдавали», а не «не заполнили».
    assert _counts(s2["parents"]) == {"total": 0, "completed": 0}


async def test_coverage_details_count_completed_in_layer(
    client: AsyncClient, admin_headers, class_scenario, db_session
) -> None:
    # Учитель дозаполняет второй вопрос — анкета про s1 становится completed.
    q_b = await _question_id_for(db_session, class_scenario["comp_b"])
    await _answer_in_campaign(
        client,
        db_session,
        "ct1@vektor.ru",
        class_scenario["ids"]["t1"],
        class_scenario["ids"]["s1"],
        class_scenario["campaign_id"],
        q_b,
        3,
    )

    body = (
        await client.get(
            f"/results/campaigns/{class_scenario['campaign_id']}/coverage", headers=admin_headers
        )
    ).json()

    s1 = _student_row(body, class_scenario["class_id"], class_scenario["ids"]["s1"])
    assert _counts(s1["teachers"]) == {"total": 1, "completed": 1}
    # Родитель свою анкету не трогал — слои считаются независимо.
    assert _counts(s1["parents"]) == {"total": 1, "completed": 0}


async def test_coverage_details_follow_class_snapshot(
    client: AsyncClient, admin_headers, class_scenario, db_session
) -> None:
    # Ученик без снапшота класса уезжает в строку «без класса» вместе со
    # своими слоями, а не теряется и не остаётся в прежнем классе.
    await db_session.execute(
        sa_update(Assessment)
        .where(
            Assessment.campaign_id == class_scenario["campaign_id"],
            Assessment.subject_id == class_scenario["ids"]["s2"],
        )
        .values(subject_class_id=None)
    )
    await db_session.commit()

    body = (
        await client.get(
            f"/results/campaigns/{class_scenario['campaign_id']}/coverage", headers=admin_headers
        )
    ).json()

    orphan = _student_row(body, None, class_scenario["ids"]["s2"])
    assert orphan["self_status"] == "completed"
    assert _counts(orphan["teachers"]) == {"total": 1, "completed": 0}

    in_class = next(c for c in body["groups"] if c["class_id"] == class_scenario["class_id"])
    assert [st["subject"]["id"] for st in in_class["students"]] == [class_scenario["ids"]["s1"]]


async def test_coverage_details_keep_layer_fixed_at_generation(
    client: AsyncClient, admin_headers, class_scenario, db_session
) -> None:
    """РЕГРЕССИЯ: слой берётся из Assessment.rater_role, а не из текущих связей.

    Учителя откручиваем от класса уже после генерации — его анкета обязана
    остаться в слое teachers. Иначе перевод ученика или смена состава класса
    задним числом переписывали бы картину прошлой кампании.
    """
    await client.request(
        "DELETE",
        f"/classes/{class_scenario['class_id']}/teachers/{class_scenario['ids']['t1']}",
        headers=admin_headers,
    )

    body = (
        await client.get(
            f"/results/campaigns/{class_scenario['campaign_id']}/coverage", headers=admin_headers
        )
    ).json()

    s1 = _student_row(body, class_scenario["class_id"], class_scenario["ids"]["s1"])
    assert _counts(s1["teachers"]) == {"total": 1, "completed": 0}
    assert _counts(s1["peers"]) == {"total": 0, "completed": 0}


# ---------- Состав класса с прогрессом (экран учителя «Мои классы») ----------


async def test_roster_visible_to_teacher_and_admin(
    client: AsyncClient, admin_headers, class_scenario
) -> None:
    teacher_headers = await _login(client, "ct1@vektor.ru")
    for headers in (teacher_headers, admin_headers):
        response = await client.get(
            f"/results/class/{class_scenario['class_id']}/roster", headers=headers
        )
        assert response.status_code == 200
        assert response.json()["class_label"] == "7-к"


async def test_roster_forbidden_for_student_and_parent(client: AsyncClient, class_scenario) -> None:
    # Те же права, что у профиля класса: список одноклассников с баллами —
    # не то, что показывают ученику или родителю.
    for email in ("cs1@vektor.ru", "cp1@vektor.ru"):
        headers = await _login(client, email)
        response = await client.get(
            f"/results/class/{class_scenario['class_id']}/roster", headers=headers
        )
        assert response.status_code == 403, email


async def test_roster_rows_carry_progress_and_scores(
    client: AsyncClient, admin_headers, class_scenario
) -> None:
    response = await client.get(
        f"/results/class/{class_scenario['class_id']}/roster", headers=admin_headers
    )
    body = response.json()
    rows = {row["subject"]["id"]: row for row in body["students"]}

    s1, s2 = class_scenario["ids"]["s1"], class_scenario["ids"]["s2"]
    assert body["students_count"] == 2
    # Выдано анкет: про s1 — три (сам, учитель, родитель), про s2 — две
    # (родителя у него нет). Завершены только самооценки: учитель и родитель
    # ответили на один вопрос из двух, их анкеты остались in_progress.
    # total и completed обязаны расходиться — иначе экран учителя показывал бы
    # 100% там, где три анкеты из пяти не дозаполнены.
    assert rows[s1]["assessments_total"] == 3
    assert rows[s1]["assessments_completed"] == 1
    assert rows[s2]["assessments_total"] == 2
    assert rows[s2]["assessments_completed"] == 1
    assert body["assessments_total"] == 5
    assert body["assessments_completed"] == 2
    assert body["coverage_percent"] == 40.0
    assert rows[s1]["self_status"] == "completed"

    # Итог = среднее по критериям ученика: у s1 (2.0 + 5.0) / 2, у s2 (4.0 + 5.0) / 2.
    assert rows[s1]["overall_avg"] == 3.5
    assert rows[s2]["overall_avg"] == 4.5

    # Прошлого периода в сценарии нет — дельты быть не должно, а не 0.0:
    # ноль читался бы как «роста не случилось».
    assert rows[s1]["delta"] is None
    assert body["average_delta"] is None

    # Зоны роста считаются той же функцией, что и в личных результатах: у s1
    # оба критерия с баллом, значит оба и попадают в зоны (их всего два).
    assert rows[s1]["growth_zone_count"] == 2


async def test_roster_includes_current_student_without_assessments(
    client: AsyncClient, admin_headers, class_scenario
) -> None:
    """Ученик, добавленный в класс после генерации, обязан быть в списке.

    Иначе учитель просто не увидит, что диагностика по нему не выдана:
    строка не появится вовсе, и отсутствие прочитается как «всё в порядке».
    """
    s3 = await _register(client, "cs3@vektor.ru", "student")
    await client.post(
        f"/classes/{class_scenario['class_id']}/students",
        json={"student_ids": [s3]},
        headers=admin_headers,
    )

    response = await client.get(
        f"/results/class/{class_scenario['class_id']}/roster", headers=admin_headers
    )
    body = response.json()
    rows = {row["subject"]["id"]: row for row in body["students"]}

    assert s3 in rows
    # None, а не not_started: анкета не выдана — это другое состояние, чем
    # выдана и не начата, и действие учителя тут другое.
    assert rows[s3]["self_status"] is None
    assert rows[s3]["assessments_total"] == 0
    assert rows[s3]["overall_avg"] is None
    assert body["students_count"] == 3


async def test_roster_unknown_class_404(client: AsyncClient, admin_headers) -> None:
    response = await client.get("/results/class/99999/roster", headers=admin_headers)
    assert response.status_code == 404


async def test_roster_still_works_for_campaign_in_progress(
    client: AsyncClient, admin_headers, class_scenario, db_session
) -> None:
    """Мониторинг хода диагностики — исключение из правила «только завершённые».

    Состав класса с прогрессом («по кому анкеты ещё не заполнены») имеет смысл
    ИМЕННО во время идущей кампании, поэтому 409 тут был бы регрессией. Балльный
    экран профиля класса на той же кампании — наоборот, закрыт.
    """
    class_id = class_scenario["class_id"]
    await _set_campaign_status(db_session, class_scenario["campaign_id"], CampaignStatus.ACTIVE)

    roster = await client.get(f"/results/class/{class_id}/roster", headers=admin_headers)
    assert roster.status_code == 200
    assert roster.json()["campaign_id"] == class_scenario["campaign_id"]

    profile = await client.get(f"/results/class/{class_id}", headers=admin_headers)
    # Незавершённая кампания в резолюцию профиля не попадает: других кампаний у
    # класса нет, поэтому «результатов пока нет».
    assert profile.status_code == 404


# --- Права: руководитель кейса видит результаты своих учеников (Этап 8) ---


async def test_results_visible_to_case_teacher(
    client: AsyncClient, admin_headers, results_scenario, db_session
) -> None:
    """Учитель кейса — полноправный учитель ученика, хоть и не ведёт его класс.

    Иначе руководитель кружка не увидел бы результаты собственных подопечных:
    ученики кейса по определению из разных классов, и учителем каждого из них
    он не числится. Решение заказчика от 2026-09-02.
    """
    ids = results_scenario["ids"]
    campaign_id = results_scenario["campaign_id"]
    await _set_campaign_status(db_session, campaign_id, CampaignStatus.CLOSED)

    case_teacher = await _register(client, "case-teacher@vektor.ru", "teacher")
    kase = (await client.post("/cases", json={"name": "Кружок прав"}, headers=admin_headers)).json()
    await client.post(
        f"/cases/{kase['id']}/teachers", json={"user_ids": [case_teacher]}, headers=admin_headers
    )

    headers = await _login(client, "case-teacher@vektor.ru")
    # Пока ученик не в кейсе, учитель кейса для него — посторонний.
    before = await client.get(f"/results/{ids['s1']}?campaign_id={campaign_id}", headers=headers)
    assert before.status_code == 403

    await client.post(
        f"/cases/{kase['id']}/students", json={"user_ids": [ids["s1"]]}, headers=admin_headers
    )

    after = await client.get(f"/results/{ids['s1']}?campaign_id={campaign_id}", headers=headers)
    assert after.status_code == 200


async def test_case_teacher_does_not_see_other_students(
    client: AsyncClient, admin_headers, results_scenario, db_session
) -> None:
    """Доступ даёт членство в ЕГО кейсе, а не наличие кейса вообще."""
    ids = results_scenario["ids"]
    campaign_id = results_scenario["campaign_id"]
    await _set_campaign_status(db_session, campaign_id, CampaignStatus.CLOSED)

    case_teacher = await _register(client, "case-teacher2@vektor.ru", "teacher")
    kase = (
        await client.post("/cases", json={"name": "Кружок прав 2"}, headers=admin_headers)
    ).json()
    await client.post(
        f"/cases/{kase['id']}/teachers", json={"user_ids": [case_teacher]}, headers=admin_headers
    )
    await client.post(
        f"/cases/{kase['id']}/students", json={"user_ids": [ids["s1"]]}, headers=admin_headers
    )

    headers = await _login(client, "case-teacher2@vektor.ru")
    response = await client.get(f"/results/{ids['s2']}?campaign_id={campaign_id}", headers=headers)

    assert response.status_code == 403


# --- Покрытие: кейсы отдельными строками и поимённый состав слоёв ---


async def test_coverage_puts_case_assessments_in_their_own_row(
    client: AsyncClient, admin_headers, class_scenario
) -> None:
    """Анкеты кружка не растворяются в классах его участников.

    До этого среза группировка шла по одному subject_class_id, а он
    проставлен и у кейсовых анкет (от него зависит видимость возрастных
    вопросов) — поэтому диагностика кейса приплюсовывалась к классу, и
    админ не видел, выдана ли она вообще.
    """
    ids = class_scenario["ids"]
    kase = (
        await client.post("/cases", json={"name": "Кружок покрытия"}, headers=admin_headers)
    ).json()
    await client.post(
        f"/cases/{kase['id']}/students", json={"user_ids": [ids["s1"]]}, headers=admin_headers
    )
    await client.post(
        f"/cases/{kase['id']}/teachers", json={"user_ids": [ids["t1"]]}, headers=admin_headers
    )

    campaign_id = (
        await client.post(
            "/campaigns",
            json={"title": "Кампания кейса", "period_year": 2026, "period_month": 9},
            headers=admin_headers,
        )
    ).json()["id"]
    await client.post(
        f"/campaigns/{campaign_id}/generate",
        json={"case_ids": [kase["id"]]},
        headers=admin_headers,
    )

    body = (
        await client.get(f"/results/campaigns/{campaign_id}/coverage", headers=admin_headers)
    ).json()

    assert [g["kind"] for g in body["groups"]] == ["case"]
    row = body["groups"][0]
    assert row["case_name"] == "Кружок покрытия"
    # Класс у строки кейса не указан, хотя на анкетах снапшот класса есть:
    # ученики кружка из разных классов, и один из них в заголовке был бы враньём.
    assert row["class_id"] is None
    # self(s1) + teacher(t1→s1) + parent(p1→s1) = 3: родители в кейсовой
    # кампании выдаются так же, как в классовой. Сумма строк сходится с итогом.
    assert row["total"] == 3
    assert sum(g["total"] for g in body["groups"]) == body["total"] == 3


async def test_coverage_layer_lists_raters_with_status(
    client: AsyncClient, admin_headers, class_scenario
) -> None:
    """Слой раскрывается до имён: «1 из 2» бесполезно, если непонятно, кому
    напоминать."""
    body = (
        await client.get(
            f"/results/campaigns/{class_scenario['campaign_id']}/coverage", headers=admin_headers
        )
    ).json()

    s1 = _student_row(body, class_scenario["class_id"], class_scenario["ids"]["s1"])
    assert [r["id"] for r in s1["teachers"]["raters"]] == [class_scenario["ids"]["t1"]]
    assert s1["teachers"]["raters"][0]["status"] == "in_progress"
    assert [r["id"] for r in s1["parents"]["raters"]] == [class_scenario["ids"]["p1"]]
    # Слой, который не выдавали, — пустой список, а не отсутствующее поле.
    assert s1["peers"]["raters"] == []


async def test_coverage_layer_raters_put_unfinished_first(
    client: AsyncClient, admin_headers, class_scenario, db_session
) -> None:
    """Порядок внутри слоя — сначала незаполнившие: их и ищут, раскрывая слой."""
    ids = class_scenario["ids"]
    t2 = await _register(client, "cov-t2@vektor.ru", "teacher")
    await client.post(
        f"/classes/{class_scenario['class_id']}/teachers",
        json={"teacher_ids": [t2]},
        headers=admin_headers,
    )
    await client.post(
        f"/campaigns/{class_scenario['campaign_id']}/generate",
        json={"class_ids": [class_scenario["class_id"]]},
        headers=admin_headers,
    )
    # Первый учитель дозаполняет свою анкету про s1 — она становится completed.
    q_b = await _question_id_for(db_session, class_scenario["comp_b"])
    await _answer_in_campaign(
        client,
        db_session,
        "ct1@vektor.ru",
        ids["t1"],
        ids["s1"],
        class_scenario["campaign_id"],
        q_b,
        3,
    )

    body = (
        await client.get(
            f"/results/campaigns/{class_scenario['campaign_id']}/coverage", headers=admin_headers
        )
    ).json()

    s1 = _student_row(body, class_scenario["class_id"], ids["s1"])
    raters = s1["teachers"]["raters"]
    assert _counts(s1["teachers"]) == {"total": 2, "completed": 1}
    assert raters[0]["id"] == t2
    assert raters[0]["status"] != "completed"
    assert raters[-1]["status"] == "completed"


async def test_coverage_student_appears_in_both_class_and_case_rows(
    client: AsyncClient, admin_headers, class_scenario
) -> None:
    """Ученик, попавший в кампанию и классом, и кейсом, виден в ОБЕИХ строках.

    Регрессия: пока строка ученика раскладывалась по одному ключу на
    субъекта, первая же встреченная анкета «застолбила» группу — и строка
    кейса получалась с ненулевым счётчиком, но пустым списком учеников, то
    есть просто не раскрывалась.
    """
    ids = class_scenario["ids"]
    kase = (
        await client.post("/cases", json={"name": "Кружок обеих строк"}, headers=admin_headers)
    ).json()
    await client.post(
        f"/cases/{kase['id']}/students", json={"user_ids": [ids["s1"]]}, headers=admin_headers
    )
    await client.post(
        f"/cases/{kase['id']}/teachers", json={"user_ids": [ids["t1"]]}, headers=admin_headers
    )

    campaign_id = (
        await client.post(
            "/campaigns",
            json={"title": "Класс и кейс", "period_year": 2026, "period_month": 9},
            headers=admin_headers,
        )
    ).json()["id"]
    # Кейс генерируем ПЕРВЫМ: тогда класс добавит про s1 только новые пары, и
    # его анкеты окажутся в обеих группах — ровно тот случай, что ломался.
    await client.post(
        f"/campaigns/{campaign_id}/generate",
        json={"case_ids": [kase["id"]]},
        headers=admin_headers,
    )
    await client.post(
        f"/campaigns/{campaign_id}/generate",
        json={"class_ids": [class_scenario["class_id"]]},
        headers=admin_headers,
    )

    body = (
        await client.get(f"/results/campaigns/{campaign_id}/coverage", headers=admin_headers)
    ).json()

    case_row = next(g for g in body["groups"] if g["kind"] == "case")
    class_row = next(g for g in body["groups"] if g["kind"] == "class")
    # У непустой строки всегда есть кого показать при раскрытии.
    for row in body["groups"]:
        assert (row["total"] > 0) == (len(row["students"]) > 0)
    assert ids["s1"] in {st["subject"]["id"] for st in case_row["students"]}
    assert ids["s2"] in {st["subject"]["id"] for st in class_row["students"]}
    # Счётчики строк не задваиваются: анкета лежит ровно в одной группе.
    assert sum(g["total"] for g in body["groups"]) == body["total"]
