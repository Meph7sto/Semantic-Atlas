"""Decision node handler - Structure definition for decision nodes.

This handler defines the branch condition structure for decision nodes
without actual execution.

Note: This is for manual modeling and structure building only.
No actual execution logic is performed at this stage.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class DecisionBranchStructure:
    """Structure definition for a decision branch.

    Attributes:
        branch_id: Unique identifier for the branch
        condition_expr: Condition expression for this branch
        target_container_id: Target container for this branch
        label: Display label for the branch
    """

    branch_id: str
    condition_expr: str
    target_container_id: str
    label: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert structure to dictionary for serialization."""
        return {
            "branch_id": self.branch_id,
            "condition_expr": self.condition_expr,
            "target_container_id": self.target_container_id,
            "label": self.label,
        }


@dataclass
class DecisionNodeStructure:
    """Structure definition for a decision node.

    Decision nodes evaluate conditions to determine which branch
    to follow. The actual branching is handled by the
    edge processor based on condition expressions.

    Attributes:
        branches: List of decision branches
        default_branch: Default branch if no conditions match
        fallback_branch: Fallback branch for errors
        branch_strategy: Strategy for handling multiple matched branches
            - "first": Take first matching branch
            - "all": Take all matching branches
    """

    branches: List[DecisionBranchStructure]
    default_branch: Optional[str]
    fallback_branch: Optional[str]
    branch_strategy: str  # "first" or "all"

    def to_dict(self) -> Dict[str, Any]:
        """Convert structure to dictionary for serialization."""
        return {
            "branches": [b.to_dict() for b in self.branches],
            "default_branch": self.default_branch,
            "fallback_branch": self.fallback_branch,
            "branch_strategy": self.branch_strategy,
        }


class DecisionNodeHandler:
    """Handler for decision node structure definition.

    This handler provides structure definitions for decision nodes
    without actual execution.

    Note: No actual AgentRunner or LLM execution is performed.
    Only structure building.
    """

    def build_structure(
        self,
        container: "AgentContainer",
        outgoing_edges: List[Any],
    ) -> DecisionNodeStructure:
        """Build structure definition for a decision node.

        Args:
            container: The AgentContainer to build structure for
            outgoing_edges: List of outgoing edges from this container

        Returns:
            DecisionNodeStructure definition

        Future Integration Point:
            When LLM execution is added, this method will:
            1. Evaluate condition expressions from outgoing edges
            2. Select branch(es) based on branch_strategy
            3. Follow selected branch to next container
        """
        config = container.config or {}

        # Build branches from outgoing edges
        branches = []
        for edge in outgoing_edges:
            branches.append(
                DecisionBranchStructure(
                    branch_id=edge.edge_id,
                    condition_expr=edge.condition_expr or "True",
                    target_container_id=edge.target_container_id,
                    label=edge.label,
                )
            )

        # Extract default and fallback branches from config
        default_branch = config.get("default_branch")
        fallback_branch = config.get("fallback_branch")

        # Extract branch strategy
        branch_strategy = config.get("branch_strategy", "first")

        return DecisionNodeStructure(
            branches=branches,
            default_branch=default_branch,
            fallback_branch=fallback_branch,
            branch_strategy=branch_strategy,
        )
