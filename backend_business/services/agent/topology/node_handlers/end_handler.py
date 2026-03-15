"""End node handler - Structure definition for end nodes.

This handler defines the output collection structure for end nodes
without actual execution.

Note: This is for manual modeling and structure building only.
No actual execution logic is performed at this stage.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class EndNodeStructure:
    """Structure definition for an end node.

    End nodes finalize the execution flow by collecting
    and formatting the final output.

    Attributes:
        output_format: Format specification for final output
        output_mapping: Mapping of node outputs to final output
        completion_actions: Actions to perform on completion
        success_criteria: Criteria for considering execution successful
    """

    output_format: Dict[str, Any]
    output_mapping: Dict[str, str]
    completion_actions: List[Dict[str, Any]]
    success_criteria: Optional[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert structure to dictionary for serialization."""
        return {
            "output_format": self.output_format,
            "output_mapping": self.output_mapping,
            "completion_actions": self.completion_actions,
            "success_criteria": self.success_criteria,
        }


class EndNodeHandler:
    """Handler for end node structure definition.

    This handler provides structure definitions for end nodes
    without actual execution.

    Note: No actual AgentRunner or LLM execution is performed.
    Only structure building.
    """

    def build_structure(
        self,
        container: "AgentContainer",
        incoming_edges: List[Any],
    ) -> EndNodeStructure:
        """Build structure definition for an end node.

        Args:
            container: The AgentContainer to build structure for
            incoming_edges: List of incoming edges to this container

        Returns:
            EndNodeStructure definition

        Future Integration Point:
            When LLM execution is added, this method will:
            1. Collect final output from incoming edges
            2. Apply output mapping
            3. Format output according to output_format
            4. Execute completion actions
            5. Mark execution as completed
        """
        config = container.config or {}

        # Extract output format from config
        output_format = config.get("output_format", {"type": "raw"})

        # Extract output mapping from config
        output_mapping = config.get("output_mapping", {})

        # Extract completion actions from config
        completion_actions = config.get("completion_actions", [])

        # Extract success criteria from config
        success_criteria = config.get("success_criteria")

        return EndNodeStructure(
            output_format=output_format,
            output_mapping=output_mapping,
            completion_actions=completion_actions,
            success_criteria=success_criteria,
        )
