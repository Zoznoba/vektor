from enum import StrEnum


class UserRole(StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    PARENT = "parent"
    ADMIN = "admin"
