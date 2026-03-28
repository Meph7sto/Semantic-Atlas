"""
Requirements deduplication service public API
"""

from .detector import DuplicateDetector
from .executor import DeduplicationExecutor
from .merger import RequirementMerger
from .models import (
    DeduplicationResult,
    DuplicateGroup,
    MergeDecision,
    MergeResult,
    PairwiseDecision,
    PairwiseRewrite,
)
from .service import RequirementsDeduplicationService

__all__ = [
    "RequirementsDeduplicationService",
    "DuplicateDetector",
    "RequirementMerger",
    "DeduplicationExecutor",
    "DuplicateGroup",
    "MergeDecision",
    "MergeResult",
    "PairwiseDecision",
    "PairwiseRewrite",
    "DeduplicationResult",
]
