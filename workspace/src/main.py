"""Main entry point for the test application."""

from src.utils import greet
from src.models.user import User


def main():
    user = User("Alice", "admin")
    print(f"Starting application for {user.name}")
    print(greet(user.name))
    print(f"Access level: {user.role}")


if __name__ == "__main__":
    main()
