import pytest

from backend_business.services.requirements_manage_service import RequirementsManageService


def test_get_allowed_status_transitions_returns_sorted_values():
    transitions = RequirementsManageService.get_allowed_status_transitions("under_review")
    assert transitions == ["archived", "confirmed", "draft", "under_review"]


def test_validate_status_transition_allows_supported_path():
    RequirementsManageService._validate_status_transition(
        "confirmed", "in_progress", "low_level"
    )


def test_validate_status_transition_rejects_unsupported_path():
    with pytest.raises(ValueError) as exc:
        RequirementsManageService._validate_status_transition(
            "completed", "in_progress", "low_level"
        )

    text = str(exc.value)
    assert "状态流转不允许" in text
    assert "completed -> in_progress" in text
    assert "允许流转" in text
