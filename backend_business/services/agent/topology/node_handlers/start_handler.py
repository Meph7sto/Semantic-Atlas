"""Start node handler - Structure definition for start nodes.

This handler defines the input validation structure for start nodes
without actual execution.

Note: This is for manual modeling and structure building only.
No actual execution logic is performed at this stage.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class StartNodeStructure:
    """Structure definition for a start node.

    Start nodes initialize the execution flow by validating
    initial input and preparing the context.

    Attributes:
        input_validation_rules: List of input validation rules
        context_preparation: Context preparation configuration
        required_fields: Required fields in initial input
    """

    input_validation_rules: List[Dict[str, Any]]
    context_preparation: Dict[str, Any]
    required_fields: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert structure to dictionary for serialization."""
        return {
            "input_validation_rules": self.input_validation_rules,
            "context_preparation": self.context_preparation,
            "required_fields": self.required_fields,
        }


class StartNodeHandler:
    """Handler for start node structure definition.

    This handler provides structure definitions for start nodes
    without actual execution.

    Note: No actual runtime execution is performed.
    Only structure building.
    """

    def build_structure(self, container: "AgentContainer") -> StartNodeStructure:
        """Build structure definition for a start node.

        Args:
            container: The AgentContainer to build structure for

        Returns:
            StartNodeStructure definition

        Future Integration Point:
            When runtime execution is added, this method will:
            1. Validate initial input against schema
            2. Prepare execution context
            3. Hand off to the configured runtime entrypoint if needed
        """
        config = container.config or {}

        # Extract validation rules from config
        input_validation_rules = config.get("input_validation_rules", [])

        # Extract context preparation from config
        context_preparation = config.get("context_preparation", {})

        # Extract required fields from input schema
        required_fields = [
            field.get("name", "")
            for field in container.input_schema
            if field.get("required", False)
        ]

        return StartNodeStructure(
            input_validation_rules=input_validation_rules,
            context_preparation=context_preparation,
            required_fields=required_fields,
        )
