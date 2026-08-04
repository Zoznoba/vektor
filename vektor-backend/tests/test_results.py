# Срез 5a: чистые доменные функции results/service.py. Без БД — синтетические
# ScoredAnswer, тот же стиль, что test_scale.py / тесты build_pairs.

from vektor.modules.results.service import (
    ScoredAnswer,
    aggregate_by_competency_and_rater,
    classify_rater_role,
    compute_gap,
    overall_by_competency,
    peers_ok,
    pick_growth_zones,
)
from vektor.shared.enums import RaterRole

TEACHER_IDS = {10, 11}
PARENT_IDS = {20, 21}


# --- classify_rater_role ---


def test_classify_rater_role_self() -> None:
    assert classify_rater_role(1, 1, TEACHER_IDS, PARENT_IDS) == RaterRole.SELF


def test_classify_rater_role_teacher() -> None:
    assert classify_rater_role(10, 1, TEACHER_IDS, PARENT_IDS) == RaterRole.TEACHER


def test_classify_rater_role_parent() -> None:
    assert classify_rater_role(20, 1, TEACHER_IDS, PARENT_IDS) == RaterRole.PARENT


def test_classify_rater_role_peer_by_default() -> None:
    assert classify_rater_role(2, 1, TEACHER_IDS, PARENT_IDS) == RaterRole.PEER


# --- peers_ok ---


def test_peers_ok_below_threshold() -> None:
    assert peers_ok(2) is False


def test_peers_ok_at_threshold() -> None:
    assert peers_ok(3) is True


def test_peers_ok_above_threshold() -> None:
    assert peers_ok(4) is True


def test_peers_ok_custom_threshold() -> None:
    assert peers_ok(4, threshold=5) is False
    assert peers_ok(5, threshold=5) is True


# --- aggregate_by_competency_and_rater ---


def test_aggregate_averages_multiple_answers_same_role() -> None:
    answers = [
        ScoredAnswer(competency_id=1, rater_role=RaterRole.PEER, value=3),
        ScoredAnswer(competency_id=1, rater_role=RaterRole.PEER, value=5),
    ]
    assert aggregate_by_competency_and_rater(answers) == {1: {RaterRole.PEER: 4.0}}


def test_aggregate_keeps_competencies_and_roles_separate() -> None:
    answers = [
        ScoredAnswer(competency_id=1, rater_role=RaterRole.SELF, value=4),
        ScoredAnswer(competency_id=1, rater_role=RaterRole.TEACHER, value=2),
        ScoredAnswer(competency_id=2, rater_role=RaterRole.SELF, value=5),
    ]
    assert aggregate_by_competency_and_rater(answers) == {
        1: {RaterRole.SELF: 4.0, RaterRole.TEACHER: 2.0},
        2: {RaterRole.SELF: 5.0},
    }


def test_aggregate_empty_answers() -> None:
    assert aggregate_by_competency_and_rater([]) == {}


def test_aggregate_role_without_answers_is_absent() -> None:
    answers = [ScoredAnswer(competency_id=1, rater_role=RaterRole.SELF, value=4)]
    result = aggregate_by_competency_and_rater(answers)
    assert RaterRole.PEER not in result[1]


# --- overall_by_competency ---


def test_overall_includes_self_with_other_roles() -> None:
    role_scores = {1: {RaterRole.SELF: 4.0, RaterRole.TEACHER: 2.0}}
    assert overall_by_competency(role_scores, peers_are_ok=True) == {1: 3.0}


def test_overall_excludes_peer_when_not_ok() -> None:
    role_scores = {1: {RaterRole.SELF: 4.0, RaterRole.PEER: 2.0}}
    assert overall_by_competency(role_scores, peers_are_ok=False) == {1: 4.0}


def test_overall_includes_peer_when_ok() -> None:
    role_scores = {1: {RaterRole.SELF: 4.0, RaterRole.PEER: 2.0}}
    assert overall_by_competency(role_scores, peers_are_ok=True) == {1: 3.0}


def test_overall_drops_competency_left_without_roles() -> None:
    role_scores = {1: {RaterRole.PEER: 4.0}}
    assert overall_by_competency(role_scores, peers_are_ok=False) == {}


# --- compute_gap ---


def test_compute_gap_present_in_both() -> None:
    assert compute_gap({1: 4.0}, {1: 3.0}) == {1: 1.0}


def test_compute_gap_missing_on_either_side_is_dropped() -> None:
    assert compute_gap({1: 4.0, 2: 3.0}, {1: 3.0}) == {1: 1.0}
    assert compute_gap({1: 4.0}, {1: 3.0, 2: 2.0}) == {1: 1.0}


# --- pick_growth_zones ---


def test_pick_growth_zones_lowest_first() -> None:
    scores = {1: 4.0, 2: 2.0, 3: 3.0, 4: 5.0}
    assert pick_growth_zones(scores, n=3) == [2, 3, 1]


def test_pick_growth_zones_tie_broken_by_competency_id() -> None:
    scores = {3: 2.0, 1: 2.0, 2: 2.0}
    assert pick_growth_zones(scores, n=2) == [1, 2]


def test_pick_growth_zones_n_larger_than_available() -> None:
    scores = {1: 4.0, 2: 2.0}
    assert pick_growth_zones(scores, n=5) == [2, 1]
