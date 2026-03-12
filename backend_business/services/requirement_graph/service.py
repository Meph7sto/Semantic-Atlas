"""
Public service facade for requirement graph generation.

The implementation is intentionally kept in a separate orchestrator module so
the package entrypoint stays small and stable, similar to
`backend_business.services.requirements_extraction.service`.
"""

from .orchestrator import RequirementGraphService, _GraphBuilder, _as_list, _req_node_id

__all__ = [
    "RequirementGraphService",
    "_GraphBuilder",
    "_as_list",
    "_req_node_id",
]
