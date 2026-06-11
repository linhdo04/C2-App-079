"""Restricted arithmetic calculator."""

import ast
import math
import operator
from collections.abc import Callable

from pydantic import BaseModel, Field

from ..react import Tool, ToolContext

MAX_ABS_VALUE = 1e100
_BINARY: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class CalculatorInput(BaseModel):
    expression: str = Field(min_length=1, max_length=200)


class CalculatorTool(Tool):
    name = "calculator"
    description = "Evaluate a restricted arithmetic expression."
    input_model = CalculatorInput

    async def execute(self, tool_input: BaseModel, context: ToolContext) -> str:
        data = CalculatorInput.model_validate(tool_input)
        try:
            value = _evaluate(ast.parse(data.expression, mode="eval").body)
        except (SyntaxError, ValueError, ZeroDivisionError, OverflowError):
            return "Biểu thức không hợp lệ hoặc không được hỗ trợ."
        return str(int(value) if value.is_integer() else value)


def _evaluate(node: ast.AST, depth: int = 0) -> float:
    if depth > 20:
        raise ValueError("Expression is too deep")
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        value = float(node.value)
    elif isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left = _evaluate(node.left, depth + 1)
        right = _evaluate(node.right, depth + 1)
        if isinstance(node.op, ast.Pow) and abs(right) > 20:
            raise ValueError("Exponent is too large")
        value = float(_BINARY[type(node.op)](left, right))
    elif isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        value = float(_UNARY[type(node.op)](_evaluate(node.operand, depth + 1)))
    else:
        raise ValueError("Unsupported expression")
    if not math.isfinite(value) or abs(value) > MAX_ABS_VALUE:
        raise ValueError("Result is too large")
    return value


__all__ = ["CalculatorInput", "CalculatorTool"]
