"""User model for the test application."""

from dataclasses import dataclass


@dataclass
class User:
    name: str
    role: str

    def is_admin(self) -> bool:
        return self.role == "admin"

    def is_editor(self) -> bool:
        return self.role in ("admin", "editor")

    def __str__(self) -> str:
        return f"User({self.name!r}, role={self.role!r})"
