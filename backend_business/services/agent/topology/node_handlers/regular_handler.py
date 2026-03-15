"""Regular node handler - Structure definition for regular nodes.

This handler defines the input/output mapping structure for regular nodes
without actual execution.

Note: This is for manual modeling and structure building only.
No actual execution logic is performed at this stage.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class RegularNodeStructure:
    """Structure definition for a regular node.

    Regular nodes are the main processing nodes that can be
    human, agent, or system role types.

    Attributes:
        input_mapping: Mapping of incoming data to node inputs
        output_mapping: Mapping of node outputs to outgoing data
        agent_id: Mapped agent ID (for role_type='agent')
        system_task_id: System task ID (for role_type='system')
        human_workflow_id: Human workflow ID (for role_type='human')
    """

    input_mapping: Dict[str, str]
    output_mapping: Dict[str, str]
    agent_id: Optional[str]
    system_task_id: Optional[str]
    human_workflow_id: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert structure to dictionary for serialization."""
        return {
            "input_mapping": self.input_mapping,
            "output_mapping": self.output_mapping,
            "agent_id": self.agent_id,
            "system_task_id": self.system_task_id,
            "human_workflow_id": self.human_workflow_id,
        }


class RegularNodeHandler:
    """Handler for regular node structure definition.

    This handler provides structure definitions for regular nodes
    without actual execution.

    Note: No actual runtime execution is performed.
    Only structure building.
    """

    def build_structure(self, container: "AgentContainer") -> RegularNodeStructure:
        """Build structure definition for a regular node.

        Args:
            container: The AgentContainer to build structure for

        Returns:
            RegularNodeStructure definition

        Future Integration Point:
            When runtime execution is added, this method will:
            1. For role_type='agent': Dispatch to the configured container entrypoint
            2. For role_type='system': Execute system task
            3. For role_type='human': Wait for human input
            4. Apply input/output mappings
        """
        config = container.config or {}

        # Extract input/output mappings from config
        input_mapping = config.get("input_mapping", {})
        output_mapping = config.get("output_mapping", {})

        # Extract role-specific IDs from config
        agent_id = config.get("agent_id")
        system_task_id = config.get("system_task_id")
        human_workflow_id = config.get("human_workflow_id")

        return RegularNodeStructure(
            input_mapping=input_mapping,
            output_mapping=output_mapping,
            agent_id=agent_id,
            system_task_id=system_task_id,
            human_workflow_id=human_workflow_id,
        )
