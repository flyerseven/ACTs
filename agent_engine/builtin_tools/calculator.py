"""Safe calculator tool using AST whitelist (no eval)."""
from __future__ import annotations

import ast
import math


_ALLOWED_NODES: set[type] = {
    ast.Expression, ast.Constant, ast.BinOp, ast.UnaryOp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd,
    ast.Call, ast.Name,
}

_ALLOWED_FUNCTIONS: dict[str, object] = {
    "abs": abs, "round": round, "min": min, "max": max,
    "sqrt": math.sqrt, "log": math.log, "log10": math.log10,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "ceil": math.ceil, "floor": math.floor,
    "pi": math.pi, "e": math.e,
}


def calculate(expression: str) -> str:
    """Safely evaluate a mathematical expression.

    Supported: +, -, *, /, //, %, **, abs, round, min, max, sqrt, log, sin, cos, etc.

    Args:
        expression: A mathematical expression string, e.g. "2 + 3 * 4"
    """
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as e:
        return f"Syntax error: {e}"

    for node in ast.walk(tree):
        if type(node) not in _ALLOWED_NODES:
            return f"Disallowed operation: {type(node).__name__}"
        if isinstance(node, ast.Name) and node.id not in _ALLOWED_FUNCTIONS:
            return f"Unknown name: {node.id}"

    try:
        compiled = compile(tree, "<calculator>", "eval")
        result = eval(compiled, {"__builtins__": {}}, _ALLOWED_FUNCTIONS)
        return str(result)
    except Exception as e:
        return f"Error: {e}"
