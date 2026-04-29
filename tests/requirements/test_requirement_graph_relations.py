from backend_business.services.db_service_parts.requirement_graph_relations import (
    RequirementGraphRelationsMixin,
)


class _RecordingCursor:
    def __init__(self):
        self.executed = []
        self.rowcount = 3

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params):
        self.executed.append((query, params))


class _RecordingConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self, cursor_factory=None):
        return self.cursor_instance


class _RecordingRelationsDB(RequirementGraphRelationsMixin):
    def __init__(self):
        self.cursor = _RecordingCursor()

    def _connect(self):
        return _RecordingConnection(self.cursor)


def test_delete_requirement_graph_relations_preserves_authoritative_sources():
    db = _RecordingRelationsDB()

    result = db.delete_requirement_graph_relations(project_id="P-1", session_id="S-1")

    query, params = db.cursor.executed[0]
    protected_source_kinds = params[-1]

    assert result["deleted_count"] == 3
    assert result["protected_source_kinds"] == protected_source_kinds
    assert "source_kind <> ALL" in query
    assert "trace_analysis" in protected_source_kinds
    assert "structural" in protected_source_kinds
    assert "project_id = %s" in query
    assert "session_id = %s" in query
