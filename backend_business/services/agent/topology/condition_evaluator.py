"""ConditionEvaluator - Parses, validates, and evaluates edge conditions safely."""

import ast
import builtins
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Set


@dataclass
class ParsedCondition:
    """Parsed condition expression structure."""

    expression: str
    variables: Set[str]
    functions: Set[str]
    operators: Set[str]
    is_valid: bool
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert parsed condition to dictionary for serialization."""
        return {
            "expression": self.expression,
            "variables": list(self.variables),
            "functions": list(self.functions),
            "operators": list(self.operators),
            "is_valid": self.is_valid,
            "errors": self.errors,
        }


class ConditionEvaluator:
    """Evaluates and validates edge condition expressions safely."""

    ALLOWED_FUNCTIONS: Set[str] = {
        "len",
        "str",
        "int",
        "float",
        "bool",
        "dict",
        "list",
        "set",
        "tuple",
        "any",
        "all",
        "min",
        "max",
        "sum",
        "abs",
        "round",
        "sorted",
        "reversed",
    }

    FORBIDDEN_PATTERNS: List[str] = [
        r"\b__",
        r"\bimport\b",
        r"\beval\b",
        r"\bexec\b",
        r"\bopen\b",
        r"\b__import__\b",
    ]

    def parse(self, expression: str) -> ParsedCondition:
        """Parse a condition expression and return its structure."""
        if not expression or not expression.strip():
            return ParsedCondition(
                expression=expression or "",
                variables=set(),
                functions=set(),
                operators=set(),
                is_valid=True,
                errors=[],
            )

        errors = []

        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, expression):
                errors.append(f"Expression contains forbidden pattern: {pattern}")

        try:
            tree = ast.parse(expression, mode="eval")
            variables = self._extract_variables(tree)
            functions = self._extract_functions(tree)
            operators = self._extract_operators(tree)

            forbidden_functions = functions - self.ALLOWED_FUNCTIONS
            if forbidden_functions:
                errors.append(
                    f"Function(s) not allowed: {', '.join(sorted(forbidden_functions))}"
                )
        except SyntaxError as e:
            errors.append(f"Syntax error: {e.msg}")
            return ParsedCondition(
                expression=expression,
                variables=set(),
                functions=set(),
                operators=set(),
                is_valid=False,
                errors=errors,
            )
        except Exception as e:
            errors.append(f"Parse error: {str(e)}")
            return ParsedCondition(
                expression=expression,
                variables=set(),
                functions=set(),
                operators=set(),
                is_valid=False,
                errors=errors,
            )

        return ParsedCondition(
            expression=expression,
            variables=variables,
            functions=functions,
            operators=operators,
            is_valid=len(errors) == 0,
            errors=errors,
        )

    def validate(self, expression: str, available_variables: Set[str]) -> List[str]:
        """Validate expression against available variables."""
        parsed = self.parse(expression)
        errors = list(parsed.errors)

        undefined_vars = parsed.variables - available_variables - parsed.functions
        if undefined_vars:
            errors.append(
                f"Undefined variable(s): {', '.join(sorted(undefined_vars))}"
            )

        return errors

    def _extract_variables(self, tree: ast.AST) -> Set[str]:
        """Extract variable names from AST."""
        variables = set()

        class VariableVisitor(ast.NodeVisitor):
            def visit_Name(self, node: ast.Name) -> None:
                variables.add(node.id)

        VariableVisitor().visit(tree)
        return variables

    def _extract_functions(self, tree: ast.AST) -> Set[str]:
        """Extract function names from AST."""
        functions = set()

        class FunctionVisitor(ast.NodeVisitor):
            def visit_Call(self, node: ast.Call) -> None:
                if isinstance(node.func, ast.Name):
                    functions.add(node.func.id)
                self.generic_visit(node)

        FunctionVisitor().visit(tree)
        return functions

    def _extract_operators(self, tree: ast.AST) -> Set[str]:
        """Extract operator types from AST."""
        operators = set()

        class OperatorVisitor(ast.NodeVisitor):
            def visit_Compare(self, node: ast.Compare) -> None:
                for op in node.ops:
                    operators.add(op.__class__.__name__)
                self.generic_visit(node)

            def visit_BoolOp(self, node: ast.BoolOp) -> None:
                operators.add(node.op.__class__.__name__)
                self.generic_visit(node)

            def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
                operators.add(node.op.__class__.__name__)
                self.generic_visit(node)

        OperatorVisitor().visit(tree)
        return operators

    def evaluate(self, expression: str, state: Dict[str, Any]) -> bool:
        """Safely evaluate a validated condition expression against runtime state."""
        if not expression or not expression.strip():
            return True

        parsed = self.parse(expression)
        if parsed.errors:
            raise ValueError("; ".join(parsed.errors))

        available_variables = set((state or {}).keys())
        undefined_vars = parsed.variables - available_variables - parsed.functions
        if undefined_vars:
            raise ValueError(
                f"Undefined variable(s): {', '.join(sorted(undefined_vars))}"
            )

        safe_globals = {
            "__builtins__": {},
            **{fn: getattr(builtins, fn) for fn in self.ALLOWED_FUNCTIONS},
        }
        try:
            compiled = compile(ast.parse(expression, mode="eval"), "<condition>", "eval")
            result = eval(compiled, safe_globals, state)
        except Exception as exc:
            raise ValueError(f"Condition evaluation failed: {exc}") from exc
        return bool(result)
