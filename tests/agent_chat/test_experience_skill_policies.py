from __future__ import annotations

import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.experience import ExperiencePolicyResolver
from backend_business.services.agent.experience.targets import ExperienceTarget


def test_policy_resolver_uses_target_specific_defaults():
    resolver = ExperiencePolicyResolver()

    decision_policy = resolver.resolve("session_controller_decision")
    classic_policy = resolver.resolve(
        ExperienceTarget(
            target_id="conflict_detection_classic",
            container_key="conflict_detection",
            prompt_builder_kind="",
            node_type="llm",
        )
    )

    assert decision_policy.retrieval_threshold >= 0.82
    assert decision_policy.allow_shared_patterns is False
    assert classic_policy.compiler_mode == "classic"
