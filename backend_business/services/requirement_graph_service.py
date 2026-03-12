"""
Compatibility facade for the requirement graph service package.

The implementation now lives under `backend_business.services.requirement_graph`
so this module can stay small while preserving existing import paths.
"""

from backend_business.services.requirement_graph import (
    RequirementGraphService,
    _GraphBuilder,
    _as_list,
    _req_node_id,
)

__all__ = [
    "RequirementGraphService",
    "_GraphBuilder",
    "_as_list",
    "_req_node_id",
]
