from backend_business.services.requirement_graph_service import (
    RequirementGraphService,
    _GraphBuilder,
    _as_list,
    _req_node_id,
)


def test_req_node_id_keeps_existing_prefix():
    assert _req_node_id("REQ-1") == "req:REQ-1"
    assert _req_node_id("req:REQ-1") == "req:REQ-1"


def test_as_list_accepts_json_arrays_and_plain_text():
    assert _as_list('["安全", "性能"]') == ["安全", "性能"]
    assert _as_list("安全") == ["安全"]
    assert _as_list(None) == []


def test_classification_adds_category_and_similarity_edges():
    class FakeDB:
        def get_latest_classification(self, session_id):
            assert session_id == "S-1"
            return {
                "id": 7,
                "requirements": ["用户必须登录", "管理员必须登录", "系统应加密传输"],
                "predictions": [
                    {"label": "身份认证", "requirement": "用户必须登录"},
                    {"label": "身份认证", "requirement": "管理员必须登录"},
                    {"label": "安全", "requirement": "系统应加密传输"},
                ],
            }

    builder = _GraphBuilder(limit=20)
    service = RequirementGraphService(FakeDB())
    text_index = {}
    for req_id, text in [
        ("REQ-1", "用户必须登录"),
        ("REQ-2", "管理员必须登录"),
        ("REQ-3", "系统应加密传输"),
    ]:
        node_id = _req_node_id(req_id)
        builder.add_node(
            node_id,
            kind="requirement",
            label=text,
            group="L3",
            properties={"req_id": req_id, "content": text},
        )
        text_index["".join(text.lower().split())] = [node_id]

    service._apply_classification(builder, "S-1", text_index)
    graph = builder.to_graph()

    assert builder.nodes["req:REQ-1"]["properties"]["category"] == "身份认证"
    assert builder.nodes["req:REQ-3"]["properties"]["category"] == "安全"
    assert any(edge["type"] == "SIMILAR_TO" for edge in graph["edges"])


def test_graph_stats_use_dynamic_label_distribution_without_hardcoded_labels():
    class FakeDB:
        def get_connection(self):
            raise AssertionError("No database reads needed in this unit test")

        def get_latest_classification(self, session_id):
            assert session_id == "S-1"
            return {
                "id": 8,
                "total": 3,
                "requirements": ["需求A", "需求B", "需求C"],
                "predictions": [
                    {"predicted_label": "定制标签甲", "requirement": "需求A"},
                    {"predicted_label": "定制标签乙", "requirement": "需求B"},
                    {"predicted_label": "定制标签甲", "requirement": "需求C"},
                ],
                "label_distribution": {"定制标签甲": 2, "定制标签乙": 1},
            }

    builder = _GraphBuilder(limit=10)
    text_index = {}
    for req_id, text in [("A", "需求A"), ("B", "需求B"), ("C", "需求C")]:
        node_id = _req_node_id(req_id)
        builder.add_node(node_id, "requirement", text, "L4", {"content": text})
        text_index["".join(text.lower().split())] = [node_id]

    stats = RequirementGraphService(FakeDB())._apply_classification(
        builder,
        "S-1",
        text_index,
    )

    assert stats["label_distribution"] == {"定制标签甲": 2, "定制标签乙": 1}
    assert builder.nodes["req:A"]["properties"]["category"] == "定制标签甲"
    assert builder.nodes["req:B"]["properties"]["category"] == "定制标签乙"
