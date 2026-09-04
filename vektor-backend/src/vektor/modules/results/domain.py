"""Чистая доменная часть результатов: подсчёт и агрегация без БД.

Отдельный модуль, потому что это единственная часть Этапа 5, которая
тестируется на синтетике без базы (юнит-тесты в tests/test_results.py), и
единственная, где живут доменные правила — порог анонимности, состав слоёв,
выбор зон роста. Здесь НЕТ ни одного импорта SQLAlchemy, и это инвариант:
как только сюда протечёт запрос, правила снова начнут дублироваться по
местам применения.

ГЛАВНОЕ ПРАВИЛО (из «Находок из прототипа», CLAUDE.md): если по компетенции
ответило меньше порога одноклассников — слой PEER по ЭТОЙ компетенции не
просто занижается, а исчезает целиком: не показывается никому (ни ученику,
ни учителю, ни родителю) и не участвует ни в одном агрегате.

Порог считается ПО КАЖДОЙ КОМПЕТЕНЦИИ, а не глобально «ответил хоть
что-нибудь». Анкеты заполняются частями (статус in_progress — штатный),
поэтому при глобальном подсчёте хватило бы трёх пиров, ответивших на
РАЗНЫЕ вопросы, чтобы показать компетенцию с единственным ответом — и
автор вычислялся бы однозначно.

Единая точка применения правила — redact_peer_scores. Всё, что считается
дальше (overall, зоны роста, разрыв самооценки), работает с уже
отредактированными данными и поэтому не может случайно «протечь».
"""

from dataclasses import dataclass

from vektor.shared.enums import RaterRole, UserRole

DEFAULT_PEER_ANONYMITY_THRESHOLD = 3
DEFAULT_GROWTH_ZONES_COUNT = 3


@dataclass(frozen=True)
class ScoredAnswer:
    """Один ответ, привязанный к компетенции и роли оценивающего.

    respondent_id нужен именно для подсчёта РАЗНЫХ одноклассников: порог
    анонимности — про число людей, а не число ответов (иначе один человек
    «набрал» бы порог сам, ответив на несколько вопросов компетенции).
    """

    competency_id: int
    rater_role: RaterRole
    respondent_id: int
    value: int


def can_disclose_peer_scores(
    peer_rater_count: int, threshold: int = DEFAULT_PEER_ANONYMITY_THRESHOLD
) -> bool:
    """Можно ли показать балл одноклассников, не выдав автора.

    peer_rater_count — число РАЗНЫХ одноклассников, ответивших по конкретной
    компетенции. Меньше порога — показывать нельзя никому.
    """
    return peer_rater_count >= threshold


def count_peer_raters_by_competency(answers: list[ScoredAnswer]) -> dict[int, int]:
    """Сколько РАЗНЫХ одноклассников ответило по каждой компетенции."""
    peers_by_competency: dict[int, set[int]] = {}
    for answer in answers:
        if answer.rater_role == RaterRole.PEER:
            peers_by_competency.setdefault(answer.competency_id, set()).add(answer.respondent_id)
    return {
        competency_id: len(respondents)
        for competency_id, respondents in peers_by_competency.items()
    }


def aggregate_by_competency_and_rater(
    answers: list[ScoredAnswer],
) -> dict[int, dict[RaterRole, float]]:
    """Сгруппировать answers по (competency_id, rater_role) и усреднить value."""
    grouped: dict[int, dict[RaterRole, list[int]]] = {}
    for answer in answers:
        by_role = grouped.setdefault(answer.competency_id, {})
        by_role.setdefault(answer.rater_role, []).append(answer.value)

    return {
        competency_id: {role: sum(values) / len(values) for role, values in by_role.items()}
        for competency_id, by_role in grouped.items()
    }


def redact_peer_scores(
    role_scores: dict[int, dict[RaterRole, float]],
    peer_rater_counts: dict[int, int],
    threshold: int = DEFAULT_PEER_ANONYMITY_THRESHOLD,
) -> dict[int, dict[RaterRole, float]]:
    """Вырезать балл одноклассников там, где его показ выдал бы автора.

    ЕДИНСТВЕННОЕ место, где применяется правило анонимности. Всё, что
    считается после (overall, зоны роста, разрыв), получает уже безопасные
    данные — поэтому не может показать то, что показывать нельзя.
    Компетенция, у которой после вырезания не осталось ни одной роли,
    выпадает целиком.
    """
    redacted: dict[int, dict[RaterRole, float]] = {}
    for competency_id, scores in role_scores.items():
        safe = {
            role: value
            for role, value in scores.items()
            if role != RaterRole.PEER
            or can_disclose_peer_scores(peer_rater_counts.get(competency_id, 0), threshold)
        }
        if safe:
            redacted[competency_id] = safe
    return redacted


def overall_by_competency(role_scores: dict[int, dict[RaterRole, float]]) -> dict[int, float]:
    """«Итоговый» балл по компетенции — среднее по ролям оценивающих.

    SELF участвует наравне с остальными (см. totalAvg() в прототипе — self
    не взвешивается отдельно). Ожидает УЖЕ отредактированные role_scores:
    фильтрацией PEER занимается redact_peer_scores, а не эта функция.
    """
    return {
        competency_id: sum(scores.values()) / len(scores)
        for competency_id, scores in role_scores.items()
        if scores
    }


def self_by_competency(role_scores: dict[int, dict[RaterRole, float]]) -> dict[int, float]:
    """Самооценка по компетенции — первая половина «разрыва самооценки»."""
    return {
        competency_id: scores[RaterRole.SELF]
        for competency_id, scores in role_scores.items()
        if RaterRole.SELF in scores
    }


def others_by_competency(role_scores: dict[int, dict[RaterRole, float]]) -> dict[int, float]:
    """Средняя оценка ДРУГИХ (все роли, кроме SELF) по компетенции.

    Вторая половина «разрыва самооценки»: сравнивать самооценку нужно не с
    итогом (в него self входит сам, и разрыв размывается), а именно с
    окружающими. Компетенция, где ответил только сам субъект, выпадает.
    """
    result: dict[int, float] = {}
    for competency_id, scores in role_scores.items():
        others = {role: value for role, value in scores.items() if role != RaterRole.SELF}
        if others:
            result[competency_id] = sum(others.values()) / len(others)
    return result


def compute_gap(
    self_scores: dict[int, float],
    others_scores: dict[int, float],
) -> dict[int, float]:
    """Разрыв самооценки: self_scores[c] - others_scores[c] по компетенции.

    Положительный — субъект оценивает себя выше окружающих, отрицательный —
    ниже. Компетенция, которой нет в self_scores ИЛИ в others_scores, в
    результат не попадает: без обеих сторон разрыв не определён.
    """
    return {
        competency_id: self_scores[competency_id] - others_scores[competency_id]
        for competency_id in self_scores
        if competency_id in others_scores
    }


def pick_growth_zones(
    overall_scores: dict[int, float], n: int = DEFAULT_GROWTH_ZONES_COUNT
) -> list[int]:
    """Top-n компетенций с наименьшим итоговым баллом — «зоны роста».

    Сортировка по (балл, competency_id) — при равных баллах порядок
    детерминирован (меньший id раньше), тесты не будут flaky.
    """
    ordered = sorted(overall_scores.items(), key=lambda item: (item[1], item[0]))
    return [competency_id for competency_id, _ in ordered[:n]]


@dataclass(frozen=True)
class SubjectProfile:
    """Профиль одного ученика тремя срезами: итог, самооценка, окружающие.

    Считается за один проход по ответам, потому что все три получаются из
    ОДНОГО отредактированного role_scores: посчитай их порознь — и правило
    анонимности пришлось бы применять трижды, а разъехавшись, срезы дали бы
    разные ответы по одним данным.
    """

    overall: dict[int, float]
    self_scores: dict[int, float]
    others_scores: dict[int, float]


def profile_from_answers(
    answers: list[ScoredAnswer], threshold: int = DEFAULT_PEER_ANONYMITY_THRESHOLD
) -> SubjectProfile:
    """Ответы → профиль ученика. Та же цепочка, что в overall_scores_from_answers,
    только отдаёт ещё и слои self/others — они нужны агрегатам группы."""
    peer_rater_counts = count_peer_raters_by_competency(answers)
    raw_scores = aggregate_by_competency_and_rater(answers)
    role_scores = redact_peer_scores(raw_scores, peer_rater_counts, threshold)
    return SubjectProfile(
        overall=overall_by_competency(role_scores),
        self_scores=self_by_competency(role_scores),
        others_scores=others_by_competency(role_scores),
    )


def overall_scores_from_answers(
    answers: list[ScoredAnswer], threshold: int = DEFAULT_PEER_ANONYMITY_THRESHOLD
) -> dict[int, float]:
    """Ответы → итоговый балл по компетенциям, ОДНОЙ функцией.

    Вся цепочка (подсчёт пиров → агрегация → redact_peer_scores → overall)
    собрана здесь, чтобы у неё было ровно одно место. Динамика по годам и
    агрегаты класса обязаны считать так же, как страница результатов: если
    редактирование применить где-то по-другому, скрытый слой одноклассников
    «протечёт» через сравнение периодов или через средний профиль класса.
    """
    peer_rater_counts = count_peer_raters_by_competency(answers)
    raw_scores = aggregate_by_competency_and_rater(answers)
    role_scores = redact_peer_scores(raw_scores, peer_rater_counts, threshold)
    return overall_by_competency(role_scores)


# ---------- Срез 5d: динамика между периодами (чистые функции) ----------


def shared_competencies(
    current_scores: dict[int, float], previous_scores: dict[int, float]
) -> set[int]:
    """Общее ядро — компетенции, посчитанные в ОБОИХ периодах.

    Состав критериев между годами меняется: «Исследование профессиональных
    возможностей» открывается только с 9 класса. Сравнивать можно лишь то,
    что мерили и там, и там.
    """
    return set(current_scores) & set(previous_scores)


def compute_deltas(
    current_scores: dict[int, float], previous_scores: dict[int, float], core: set[int]
) -> dict[int, float]:
    """Прирост по компетенциям общего ядра: current - previous.

    Только по ядру: у критерия, появившегося в этом году, «прироста» нет —
    показать там разницу с нулём или с самим собой значило бы нарисовать
    достижение, которого не было.
    """
    return {
        competency_id: current_scores[competency_id] - previous_scores[competency_id]
        for competency_id in core
        if competency_id in current_scores and competency_id in previous_scores
    }


def core_average(scores: dict[int, float], core: set[int]) -> float | None:
    """Средний балл ТОЛЬКО по общему ядру.

    Именно этот итог сравнивают между периодами, а не overall_average из
    get_subject_results: тот считается по всем критериям своего периода, и при
    смене их состава сдвинулся бы сам по себе — без всякого роста ученика.
    """
    relevant = [scores[competency_id] for competency_id in core if competency_id in scores]
    return sum(relevant) / len(relevant) if relevant else None


# ---------- Срез 5e: агрегаты класса (чистые функции) ----------


def average_profiles(profiles: list[dict[int, float]]) -> dict[int, float]:
    """Средний профиль по списку индивидуальных профилей.

    Каждый УЧЕНИК весит одинаково, независимо от того, сколько человек его
    оценивало. Иначе ученик, про которого ответили пятеро, перевесил бы того,
    про кого ответил один, и «средний профиль класса» съехал бы в сторону
    самых охваченных.
    """
    sums: dict[int, float] = {}
    counts: dict[int, int] = {}
    for profile in profiles:
        for competency_id, value in profile.items():
            sums[competency_id] = sums.get(competency_id, 0.0) + value
            counts[competency_id] = counts.get(competency_id, 0) + 1
    return {competency_id: sums[competency_id] / counts[competency_id] for competency_id in sums}


# Меньше этого расхождения — шум на трёх вопросах, подписывать нечего. Тот
# же порог, что стоял у подписей «выше школы на …» в прежних полосах.
MEANINGFUL_DIFF = 0.3


def rank_school_gaps(
    group_scores: dict[int, float],
    school_scores: dict[int, float],
    n: int = DEFAULT_GROWTH_ZONES_COUNT,
) -> list[tuple[int, float]]:
    """Критерии, где группа ОТСТАЁТ от школы: (competency_id, отставание).

    Пришло на смену ранжированию по охвату личных зон роста (5e, удалено
    2026-09-04). У той метрики было два изъяна: она относительная (у каждого
    ученика ровно три личные зоны независимо от того, насколько плохи дела,
    поэтому критерий с 4.0 у всех мог возглавить список), и её счётчик
    «6 учеников» читался как «шестеро провалились».

    Отставание от школы отвечает на вопрос, ради которого экран и открывают:
    чем ЭТА группа отличается. Критерий, низкий у всей школы, — не проблема
    класса, а свойство методики или возраста, и вести по нему классный час
    бессмысленно.

    Возвращаются ТОЛЬКО отстающие (разница меньше −MEANINGFUL_DIFF), от
    худшего к лучшему. Группа может нигде не отставать — тогда список пуст,
    и это честный ответ, а не повод показать три случайных критерия.
    """
    gaps = [
        (competency_id, score - school_scores[competency_id])
        for competency_id, score in group_scores.items()
        if competency_id in school_scores
    ]
    behind = [(cid, gap) for cid, gap in gaps if gap <= -MEANINGFUL_DIFF]
    # Сортировка по (отставание, id): при равенстве меньший id раньше, чтобы
    # порядок не плавал между запросами.
    return sorted(behind, key=lambda item: (item[1], item[0]))[:n]


def rank_self_gaps(
    self_scores: dict[int, float],
    others_scores: dict[int, float],
    n: int = DEFAULT_GROWTH_ZONES_COUNT,
) -> list[tuple[int, float]]:
    """Критерии с наибольшим расхождением «самооценка − окружающие» по группе.

    Это единственное место, где на экране группы видно собственно 360°:
    средний балл и сравнение со школой одинаково считались бы и по обычной
    оценке учителя. Знак важен и сохраняется: «себя выше» и «себя ниже» —
    это два разных разговора с классом, а не одна «величина расхождения».

    Сортировка по МОДУЛЮ разрыва (сначала самое яркое расхождение), но в
    список попадает только то, что больше MEANINGFUL_DIFF.
    """
    gaps = [
        (competency_id, score - others_scores[competency_id])
        for competency_id, score in self_scores.items()
        if competency_id in others_scores
    ]
    meaningful = [(cid, gap) for cid, gap in gaps if abs(gap) >= MEANINGFUL_DIFF]
    return sorted(meaningful, key=lambda item: (-abs(item[1]), item[0]))[:n]


def can_view_results(
    current_user_id: int,
    current_user_role: UserRole,
    subject_id: int,
    teacher_ids: set[int],
    parent_ids: set[int],
) -> bool:
    """Кто может смотреть результаты субъекта: он сам, admin, его родитель
    (parent_ids) или учитель (teacher_ids) — под учителем понимается и учитель
    его класса, и руководитель его кейса: состав teacher_ids собирает
    вызывающий код. Чистая функция — оба множества уже посчитаны из БД."""
    return (
        current_user_id == subject_id
        or current_user_role == UserRole.ADMIN
        or current_user_id in teacher_ids
        or current_user_id in parent_ids
    )


def can_view_group_results(
    current_user_id: int,
    current_user_role: UserRole,
    teacher_ids: set[int],
) -> bool:
    """Кто видит группу (класс или кейс) целиком: admin или её учитель.

    Имя без «class» намеренно: функция ничего не знает про класс — ей
    передают множество учителей, и профиль кейса пользуется ею наравне с
    профилем класса. Классный руководитель входит в teachers по построению
    (см. classes/service.py), руководитель кейса — по составу Case.teachers.

    Родителю и ученику класс не показываем: в прототипе экран «Мой класс» с
    баллами есть только у учителя и админа. Родитель видит своего ребёнка на
    фоне среднего по классу — это другой экран и другие данные.
    """
    return current_user_role == UserRole.ADMIN or current_user_id in teacher_ids


CoverageKey = tuple[str, int | None]


def coverage_key(class_id: int | None, case_id: int | None) -> CoverageKey:
    """Основание, по которому выдана анкета: кейс важнее класса.

    Чистая функция и единственное место, где это правило живёт, — его
    применяют и агрегат, и детализация по ученикам, а разъехавшись, они дали
    бы строку класса с чужими учениками внутри.

    Кейс приоритетнее не потому, что «важнее», а потому, что специфичнее:
    subject_class_id проставляется у КАЖДОЙ анкеты (от него зависит видимость
    возрастных вопросов), в том числе у выданной за кружок. Группируй мы по
    классу, анкеты кейса растворились бы в классах его участников — ровно та
    жалоба, с которой этот срез и начался.
    """
    if case_id is not None:
        return ("case", case_id)
    if class_id is not None:
        return ("class", class_id)
    return ("none", None)


def coverage_sort_key(group: dict) -> tuple:
    """Порядок строк: сначала классы по возрастанию (8-1 перед 8-2), затем
    кейсы по алфавиту, последней — строка «без класса».

    Классы вперёд, потому что диагностика по классам — основной поток, а
    кружки — дополнение к нему; «без класса» в конце по той же причине, по
    которой раньше стоял NULLS LAST.
    """
    order = {"class": 0, "case": 1, "none": 2}[group["kind"]]
    if group["kind"] == "class":
        label = group["class_label"] or ""
        grade, _, section = label.partition("-")
        return (order, int(grade) if grade.isdigit() else 0, section)
    return (order, 0, group["case_name"] or "")
