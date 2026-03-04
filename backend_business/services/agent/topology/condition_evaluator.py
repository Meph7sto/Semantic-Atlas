"""ConditionEvaluator - Parses and validates edge condition expressions.

This class provides safe parsing and validation of condition expressions
used for edge routing. It does not evaluate expressions - only
parses and validates their structure.

Note: This is for manual modeling and structure building only.
No actual expression evaluation is performed at this stage.
"""

import ast
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Set, Optional


@dataclass
class ParsedCondition:
    """Parsed condition expression structure.

    This dataclass stores the parsed structure of a condition
    expression without actual evaluation.

    Attributes:
        expression: Original expression string
        variables: Set of variable names referenced in the expression
        functions: Set of function names called in the expression
        operators: Set of operators used in the expression
        is_valid: Whether the expression syntax is valid
        errors: List of syntax errors found
    """

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
    """Evaluates and validates edge condition expressions safely.

    This class provides structure parsing and validation for condition
    expressions used in edge routing.

    Note: Does not actually evaluate expressions - only parses
    and validates their structure for security and correctness.

    Allowed functions (safe built-ins):
        len, str, int, float, bool, dict, list, set, tuple,
        any, all, min, max, sum, abs, round, sorted, reversed

    Allowed operators:
        ==, !=, <, <=, >, >=, and, or, not, in, not in, is, is not
    """

    # Allowed functions for safe evaluation
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

    # Forbidden patterns for security
    FORBIDDEN_PATTERNS: List[str] = [
        r"\b__",  # No dunder attributes
        r"\bimport\b",  # No import statements
        r"\beval\b",  # No eval statements
        r"\bexec\b",  # No exec statements
        r"\bopen\b",  # No file operations
        r"\b__import__\b",  # No __import__ calls
    ]

    def parse(self, expression: str) -> ParsedCondition:
        """Parse a condition expression and return its structure.

        Args:
            expression: The condition expression to parse

        Returns:
            ParsedCondition object with variables, functions, operators,
            and validation status
        """
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

        # Check for forbidden patterns
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, expression):
                errors.append(
                    f"Expression contains forbidden pattern: {pattern}"
                )

        # Try to parse the expression as AST
        try:
            tree = ast.parse(expression, mode="eval")

            # Extract variables and functions
            variables = self._extract_variables(tree)
            functions = self._extract_functions(tree)
            operators = self._extract_operators(tree)

            # Validate functions are allowed
            forbidden_functions = functions - self.ALLOWED_FUNCTIONS
            if forbidden_functions:
                errors.append(
                    f"Function(s) not allowed: {', '.join(forbidden_functions)}"
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

    def validate(
        self,
        expression: str,
        available_variables: Set[str],
    ) -> List[str]:
        """Validate expression against available variables.

        Args:
            expression: The condition expression to validate
            available_variables: Set of variable names that are available

        Returns:
            List of validation errors (empty if valid)
        """
        parsed = self.parse(expression)
        errors = list(parsed.errors)

        # Check if all referenced variables are available
        undefined_vars = parsed.variables - available_variables
        if undefined_vars:
            errors.append(
                f"Undefined variable(s): {', '.join(undefined_vars)}"
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

        FunctionVisitor().visit(tree)
        return functions

    def _extract_operators(self, tree: ast.AST) -> Set[str]:
        """Extract operator types from AST."""
        operators = set()

        class OperatorVisitor(ast.NodeVisitor):
            def visit_Compare(self, node: ast.Compare) -> None:
                for op in node.ops:
                    op_name = op.__class__.__name__
                    operators.add(op_name)

            def visit_BoolOp(self, node: ast.BoolOp) -> None:
                op_name = node.op.__class__.__name__
                operators.add(op_name)

            def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
                op_name = node.op.__class__.__name__
                operators.add(op_name)

        OperatorVisitor().visit(tree)
        return operators

    # Future: Add evaluate() method when LLM integration is ready
    #
    # def evaluate(self, expression: str, state: Dict[str, Any]) -> bool:
    #     """Evaluate condition expression against current state.
    #
    #     NOTE: This method will be implemented when LLM execution is added.
    #     Currently, only parse and validate are used.
    #     """
    #     # Safe globals with only allowed functions
    #     safe_globals = {
    #         "__builtins__": {},
    #         **{fn: __builtins__[fn] for fn in self.ALLOWED_FUNCTIONS},
    #     }
    #
    #     try:
    #         result = eval(expression, safe_globals, state)
    #         return bool(result)
    #     except Exception as e:
    #         logger.warning(f"Condition evaluation failed: {expression}, error: {e}")
    #         return False  # Fail closed for safety
    #
    #     # TODO: Implement when LLM execution phase is ready
