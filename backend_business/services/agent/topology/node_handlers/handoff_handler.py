"""Handoff node handler - Structure definition for handoff nodes.

This handler defines the context transfer structure for handoff nodes
without actual execution.

Note: This is for manual modeling and structure building only.
No actual execution logic is performed at this stage.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class HandoffNodeStructure:
    """Structure definition for a handoff node.

    Handoff nodes transfer context between different workflows,
    projects, or users.

    Attributes:
        target_project_id: Target project ID (if transferring projects)
        target_user_id: Target user ID (if transferring users)
        target_context: Target context dictionary
        context_transfer_rules: Rules for what data to transfer
        context_purge_rules: Rules for what data to exclude
    """

    target_project_id: Optional[str]
    target_user_id: Optional[str]
    target_context: Dict[str, Any]
    context_transfer_rules: Dict[str, List[str]]
    context_purge_rules: Dict[str, List[str]]

    def to_dict(self) -> Dict[str, Any]:
        """Convert structure to dictionary for serialization."""
        return {
            "target_project_id": self.target_project_id,
            "target_user_id": self.target_user_id,
            "target_context": self.target_context,
            "context_transfer_rules": self.context_transfer_rules,
            "context_purge_rules": self.context_purge_rules,
        }


class HandoffNodeHandler:
    """Handler for handoff node structure definition.

    This handler provides structure definitions for handoff nodes
    without actual execution.

    Note: No actual AgentRunner or LLM execution is performed.
    Only structure building.
    """

    def build_structure(self, container: "AgentContainer") -> HandoffNodeStructure:
        """Build structure definition for a handoff node.

        Args:
            container: The AgentContainer to build structure for

        Returns:
            HandoffNodeStructure definition

        Future Integration Point:
            When LLM execution is added, this method will:
            1. Create new execution context for target
            2. Transfer selected data according to transfer_rules
            3. Purge excluded data according to purge_rules
            4. Continue execution in new context
        """
        config = container.config or {}

        # Extract handoff targets from config
        target_project_id = config.get("target_project_id")
        target_user_id = config.get("target_user_id")

        # Extract target context from config
        target_context = config.get("target_context", {})

        # Extract transfer/purge rules from config
        context_transfer_rules = config.get("context_transfer_rules", {})
        context_purge_rules = config.get("context_purge_rules", {})

        return HandoffNodeStructure(
            target_project_id=target_project_id,
            target_user_id=target_user_id,
            target_context=target_context,
            context_transfer_rules=context_transfer_rules,
            context_purge_rules=context_purge_rules,
        )
