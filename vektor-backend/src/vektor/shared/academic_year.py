from datetime import date

# Учебный год начинается в сентябре. С января по август текущая дата
# относится к учебному году, который стартовал осенью ПРЕДЫДУЩЕГО
# календарного года (например, март 2026 — учебный год «2025/2026»).
_ACADEMIC_YEAR_START_MONTH = 9


def academic_year_label(today: date) -> str:
    start_year = today.year if today.month >= _ACADEMIC_YEAR_START_MONTH else today.year - 1
    return f"{start_year}/{start_year + 1} учебный год"
