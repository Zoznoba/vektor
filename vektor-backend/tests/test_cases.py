# Интеграционные тесты cases: реальные HTTP-запросы, реальный Postgres
# (тестовая база через фикстуру client). admin_headers — в conftest.py.
#
# Скелет: имена тестов задают требуемое поведение, тела дописываются вместе с
# реализацией сервиса. Стиль — как в test_classes.py.

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


# --- POST /cases ---

# TODO: test_create_case_success — 201, пустые students/teachers
# TODO: test_create_case_duplicate_name_conflict — 409 case_already_exists
# TODO: test_create_case_forbidden_for_teacher — 403 (только админ пишет)


# --- GET /cases ---

# TODO: test_list_cases_visible_to_teacher — учителю список доступен (200)
# TODO: test_list_cases_forbidden_for_student — 403


# --- состав ---

# TODO: test_assign_students_bulk — пачкой, оба ученика в составе
# TODO: test_assign_teacher_wrong_role — ученика в учителя кейса → 409 wrong_role
# TODO: test_assign_student_already_in_another_case — 409 already_in_another_case;
#       ЗАОДНО проверить, что человек остался в ПЕРВОМ кейсе (не перевесился)
# TODO: test_assign_same_student_twice_is_noop — повторная привязка в ТОТ ЖЕ
#       кейс не ошибка (идемпотентность, как у родителей в 3.6)
# TODO: test_assign_atomic_on_error — в пачке один невалидный: в БД не осело
#       НИЧЕГО (валидация до записи; ср. test_bulk_users.py)
# TODO: test_case_is_cross_grade — ученики из двух РАЗНЫХ классов уживаются
#       в одном кейсе: это его смысл, а не краевой случай


# --- открепление и удаление ---

# TODO: test_remove_member — участник ушёл из состава, но остался в системе
# TODO: test_remove_member_not_in_case — 404 not_in_case
# TODO: test_delete_empty_case — 204
# TODO: test_delete_case_with_members_conflict — 409 case_not_empty
