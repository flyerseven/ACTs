"""Utility functions for the test application."""


def greet(name: str) -> str:
    """Return a greeting for the given name."""
    return f"Hello, {name}! Welcome to the workspace."


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Format data as a plain-text table."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    lines = []
    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    lines.append(header_line)
    lines.append("-" * len(header_line))
    for row in rows:
        lines.append(" | ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(row)))
    return "\n".join(lines)
