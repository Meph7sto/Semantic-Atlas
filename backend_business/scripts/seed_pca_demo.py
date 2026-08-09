from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend_business.config import settings
from backend_business.services.db_service_parts.schema import init_db


DEMO_SESSION_ID = "demo-pca-infusion-pump-session"
DEMO_PROJECT_NAME = "Demo · PCA患者自控镇痛输液泵"
DEMO_PROJECT_ID = "demo-pca-infusion-pump-project"
DEMO_GRAPH_INITIAL_SNAPSHOT_ID = "demo-pca-initial-structure-graph"
DEFAULT_MD_PATH = Path(
    os.environ.get(
        "PCA_DEMO_MD_PATH",
        "F:/xwechat_files/wxid_mqr3bqj6oqfw22_8ad5/msg/file/2026-08/"
        "demo_PCA输液泵原始需求清单.md",
    )
)
DEFAULT_TXT_PATH = Path(
    os.environ.get(
        "PCA_DEMO_TXT_PATH",
        "F:/xwechat_files/wxid_mqr3bqj6oqfw22_8ad5/msg/file/2026-08/"
        "demo_PCA输液泵需求调研会议记录.txt",
    )
)

TOP_ID_PREFIX = "PCA-H"
LOW_ID_PREFIX = "PCA-L"


COMPONENT_BY_TOP = {
    "H-01": "储液仓",
    "H-02": "机械泵",
    "H-03": "功能安全架构",
    "H-04": "控制面板",
    "H-05": "运行线程",
    "H-06": "事件日志",
    "H-07": "电池",
    "H-08": "电源控制",
    "H-09": "报警线程",
    "H-10": "独立故障灯",
    "H-11": "故障日志",
    "H-12": "泵故障管理器",
}

TOP_LEVEL_BY_RAW_ID = {
    "H-01": "L1",
    "H-02": "L1",
    "H-04": "L1",
    "H-07": "L1",
    "H-05": "L2",
    "H-06": "L2",
    "H-08": "L2",
    "H-09": "L2",
    "H-03": "L3",
    "H-10": "L3",
    "H-11": "L3",
    "H-12": "L3",
}

PENDING_ISSUES = [
    {
        "issue_id": "OPEN-KVO-UNIT",
        "related_ids": ["L-23"],
        "title": "KVO数值和单位不完整",
        "detail": "源需求写作 FKVO = 1/ml，会议确认不能擅自补成 1 ml/hr。",
    },
    {
        "issue_id": "OPEN-BOLUS-TOLERANCE",
        "related_ids": ["L-46", "L-47", "L-48", "L-49"],
        "title": "追加剂量流量容差缺少数值",
        "detail": "基础流量容差已明确为 0.5 ml/hr，患者追加和医护追加仍需补参数来源。",
    },
    {
        "issue_id": "OPEN-TABLE-4",
        "related_ids": ["L-23", "L-51"],
        "title": "报警与泵速响应依赖缺失的Table 4",
        "detail": "哪些报警保持原速、降到KVO或完全停泵，需要由Table 4和风险分析确认。",
    },
    {
        "issue_id": "OPEN-ALARM-SILENCE",
        "related_ids": ["H-04", "L-20", "L-50"],
        "title": "报警静音范围和最长时长待确认",
        "detail": "夜间病房需要静音状态可见，但高优先级报警是否允许静音需按IEC 60601-1-8确认。",
    },
    {
        "issue_id": "OPEN-TEMP-NAME",
        "related_ids": ["L-14"],
        "title": "55摄氏度测点和报警名称不一致",
        "detail": "标题为过热报警，正文写泵过载报警；测温位置也会影响测试方法。",
    },
    {
        "issue_id": "OPEN-LOG-OVERWRITE",
        "related_ids": ["L-36", "L-53"],
        "title": "日志容量满后的覆盖策略待确认",
        "detail": "两种日志均需保留至少1000小时，但循环覆盖/禁止覆盖/导出后覆盖尚未定义。",
    },
    {
        "issue_id": "OPEN-MASKED-FAULT",
        "related_ids": ["L-54"],
        "title": "成功屏蔽故障是否仍报警存在歧义",
        "detail": "可能是记录但不报警，也可能是影响被屏蔽但报警仍发，需安全分析关闭。",
    },
    {
        "issue_id": "OPEN-POWER-STOP",
        "related_ids": ["L-38"],
        "title": "市电与电池同时不可用时的精确停泵动作待确认",
        "detail": "需明确立即停泵、完成当前行程后停，还是先报警再停。",
    },
]


def _read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _prefixed_id(raw_id: str) -> str:
    raw_id = raw_id.strip().upper()
    if raw_id.startswith("H-"):
        return f"{TOP_ID_PREFIX}-{raw_id.split('-', 1)[1]}"
    if raw_id.startswith("L-"):
        return f"{LOW_ID_PREFIX}-{raw_id.split('-', 1)[1]}"
    return raw_id


def _short_text(value: str, max_len: int = 500) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= max_len:
        return value
    return value[: max_len - 3].rstrip() + "..."


def _stable_fingerprint(session_id: str, req_id: str, text: str) -> str:
    raw = f"pca-demo|{session_id}|{req_id}|{text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def parse_requirements_md(md_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[str]]]:
    if not md_path.exists():
        raise FileNotFoundError(f"demo md file not found: {md_path}")

    content = _read_text(md_path)
    high_reqs: list[dict[str, Any]] = []
    low_reqs: list[dict[str, Any]] = []
    relations: dict[str, list[str]] = {}

    for line in content.splitlines():
        text = line.strip()
        rel_match = re.match(r"^(H-\d{2})\s*->\s*(.+)$", text)
        if rel_match:
            raw_high, raw_lows = rel_match.groups()
            relations.setdefault(_prefixed_id(raw_high), [])
            lows = [
                _prefixed_id(item.strip())
                for item in raw_lows.split(",")
                if item.strip()
            ]
            relations[_prefixed_id(raw_high)].extend(lows)
            continue

        high_match = re.match(r"^(H-\d{2})\s+(.+)$", text)
        if high_match:
            raw_id, statement = high_match.groups()
            high_reqs.append(
                {
                    "raw_id": raw_id,
                    "req_id": _prefixed_id(raw_id),
                    "level": TOP_LEVEL_BY_RAW_ID.get(raw_id, "L3"),
                    "text": statement.strip(),
                    "component": COMPONENT_BY_TOP.get(raw_id, "PCA泵系统"),
                }
            )
            continue

        low_match = re.match(r"^(L-\d{2})\s+(.+)$", text)
        if low_match:
            raw_id, statement = low_match.groups()
            low_reqs.append(
                {
                    "raw_id": raw_id,
                    "req_id": _prefixed_id(raw_id),
                    "text": statement.strip(),
                }
            )
            continue

    if not high_reqs or not low_reqs or not relations:
        raise ValueError("demo md file did not contain H/L requirements and trace relations")

    return high_reqs, low_reqs, relations


def load_meeting_meta(txt_path: Path) -> dict[str, Any]:
    if not txt_path.exists():
        return {"source": str(txt_path), "available": False}

    text = _read_text(txt_path)
    speakers = sorted(set(re.findall(r"^([^:\n：]{1,12})[:：]", text, flags=re.MULTILINE)))
    return {
        "source": str(txt_path),
        "available": True,
        "char_count": len(text),
        "speakers": speakers,
        "pending_issues": PENDING_ISSUES,
    }


def _priority_for_text(text: str) -> str:
    high_keywords = (
        "hard limit",
        "alarm",
        "stopped immediately",
        "shall be stopped",
        "failure",
        "fault",
        "tamper",
        "reverse",
        "over-infusion",
        "overinfusion",
        "battery failure",
    )
    lowered = text.lower()
    if any(keyword in lowered for keyword in high_keywords):
        return "high"
    if any(keyword in lowered for keyword in ("warning", "retained", "timestamp", "battery", "kvo")):
        return "medium"
    return "medium"


def _classification_label(text: str, raw_id: str) -> str:
    lowered = text.lower()
    if raw_id in {"L-23", "L-46", "L-47", "L-48", "L-49", "L-51", "L-54", "L-38"}:
        return "待确认项"
    if any(word in lowered for word in ("alarm", "warning", "alert", "priority", "visual")):
        return "报警需求"
    if any(word in lowered for word in ("fault", "failure", "hard limit", "tamper", "reverse", "safety", "occlusion")):
        return "安全需求"
    if any(word in lowered for word in ("log", "timestamp", "retained", "clock", "record")):
        return "数据与日志"
    if any(word in lowered for word in ("battery", "mains", "power", "voltage", "energy")):
        return "电源需求"
    if any(word in lowered for word in ("clinician", "authorized", "confirmation", "prescription", "door", "dea")):
        return "权限与防拆"
    return "功能需求"


def _component_for_low(req_id: str, relations: dict[str, list[str]]) -> str:
    for top_id, low_ids in relations.items():
        if req_id in low_ids:
            raw_top = "H-" + top_id.rsplit("-", 1)[-1]
            return COMPONENT_BY_TOP.get(raw_top, "PCA泵系统")
    return "PCA泵系统"


def seed_demo(md_path: Path, txt_path: Path) -> dict[str, Any]:
    high_reqs, low_reqs, relations = parse_requirements_md(md_path)
    meeting_meta = load_meeting_meta(txt_path)
    low_by_id = {item["req_id"]: item for item in low_reqs}
    relation_pairs = [(top_id, low_id) for top_id, lows in relations.items() for low_id in lows]

    with psycopg2.connect(settings.POSTGRES_DSN) as conn:
        init_db(conn)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO manage_projects (
                    project_id, name, description, status, created_by,
                    created_at, updated_at, current_session_id
                )
                VALUES (%s, %s, %s, 'active', 'system', NOW(), NOW(), %s)
                ON CONFLICT (name) DO UPDATE SET
                    description = EXCLUDED.description,
                    status = 'active',
                    current_session_id = EXCLUDED.current_session_id,
                    updated_at = NOW()
                RETURNING project_id
                """,
                (
                    DEMO_PROJECT_ID,
                    DEMO_PROJECT_NAME,
                    "PCA患者自控镇痛输液泵需求调研演示项目，数据来自demo会议记录与原始需求清单。",
                    DEMO_SESSION_ID,
                ),
            )
            project_id = cur.fetchone()["project_id"]
            cur.execute(
                """
                UPDATE manage_projects
                SET current_session_id = %s, status = 'active', updated_at = NOW()
                WHERE project_id = %s
                """,
                (DEMO_SESSION_ID, project_id),
            )
            cur.execute(
                """
                INSERT INTO manage_branch_refs (
                    ref_id, project_id, ref_name, ref_type, milestone_id,
                    created_by, created_at, updated_at
                )
                VALUES (%s, %s, 'main', 'branch', NULL, 'system', NOW(), NOW())
                ON CONFLICT (project_id, ref_name) DO NOTHING
                """,
                (f"{project_id}-main", project_id),
            )

            cur.execute("DELETE FROM requirements_analysis_runs WHERE session_id = %s", (DEMO_SESSION_ID,))
            cur.execute("DELETE FROM trace_analysis WHERE session_id = %s", (DEMO_SESSION_ID,))
            cur.execute("DELETE FROM conflict_analysis WHERE session_id = %s", (DEMO_SESSION_ID,))
            cur.execute("DELETE FROM classification_analysis WHERE session_id = %s", (DEMO_SESSION_ID,))
            cur.execute("DELETE FROM requirement_graph_relations WHERE project_id = %s", (project_id,))
            cur.execute("DELETE FROM manage_requirements WHERE project_id = %s", (project_id,))
            cur.execute("DELETE FROM low_level_requirement_links WHERE session_id = %s", (DEMO_SESSION_ID,))
            cur.execute("DELETE FROM low_level_requirements WHERE session_id = %s", (DEMO_SESSION_ID,))
            cur.execute("DELETE FROM requirements_l123 WHERE session_id = %s", (DEMO_SESSION_ID,))

            for idx, req in enumerate(high_reqs, start=1):
                req_id = req["req_id"]
                source_text = req["text"]
                cur.execute(
                    """
                    INSERT INTO requirements_l123 (
                        req_id, session_id, level, text, fingerprint,
                        anchor_span_id, r, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, NULL, 2, NOW())
                    """,
                    (
                        req_id,
                        DEMO_SESSION_ID,
                        req["level"],
                        _short_text(source_text),
                        _stable_fingerprint(DEMO_SESSION_ID, req_id, source_text),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO manage_requirements (
                        req_id, project_id, requirement_type, status, title, description,
                        priority, assignee, tags, due_date, parent_id, order_index,
                        source_req_id, source_level, custom_fields,
                        created_by, created_at, updated_by, updated_at, deleted
                    )
                    VALUES (
                        %s, %s, 'top_level', 'draft', %s, %s,
                        %s, NULL, %s::jsonb, NULL, NULL, %s,
                        %s, %s, %s::jsonb,
                        'system', NOW(), 'system', NOW(), FALSE
                    )
                    """,
                    (
                        req_id,
                        project_id,
                        _short_text(source_text, 260),
                        source_text,
                        _priority_for_text(source_text),
                        json.dumps(["PCA", req["component"], "原始上层需求"], ensure_ascii=False),
                        idx,
                        req_id,
                        req["level"],
                        json.dumps(
                            {
                                "source": "demo_PCA输液泵原始需求清单.md",
                                "raw_id": req["raw_id"],
                                "component": req["component"],
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )

            for idx, req in enumerate(low_reqs, start=1):
                req_id = req["req_id"]
                top_ids = [top_id for top_id, lows in relations.items() if req_id in lows]
                primary_top_id = top_ids[0] if top_ids else None
                component = _component_for_low(req_id, relations)
                source_text = req["text"]
                open_questions = [
                    issue
                    for issue in PENDING_ISSUES
                    if req["raw_id"] in set(issue["related_ids"])
                ]
                cur.execute(
                    """
                    INSERT INTO low_level_requirements (
                        req_id, session_id, source_top_id, source_top_text,
                        text, component, acceptance_criteria, test_method,
                        interfaces, data_contracts, error_handling, nfr,
                        open_questions, evidence_ids, confidence, source, meta, created_at
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s::jsonb, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                        %s::jsonb, %s::jsonb, %s, 'pca_demo_seed', %s::jsonb, NOW()
                    )
                    """,
                    (
                        req_id,
                        DEMO_SESSION_ID,
                        primary_top_id,
                        next((r["text"] for r in high_reqs if r["req_id"] == primary_top_id), None),
                        source_text,
                        component,
                        json.dumps(["需求条目已从原始清单导入，待评审后形成验收用例"], ensure_ascii=False),
                        "review_and_test_design",
                        json.dumps([], ensure_ascii=False),
                        json.dumps([], ensure_ascii=False),
                        json.dumps([], ensure_ascii=False),
                        json.dumps([], ensure_ascii=False),
                        json.dumps(open_questions, ensure_ascii=False),
                        json.dumps([req["raw_id"], "demo-meeting"], ensure_ascii=False),
                        0.92 if not open_questions else 0.74,
                        json.dumps(
                            {
                                "source": "demo_PCA输液泵原始需求清单.md",
                                "meeting_source": meeting_meta.get("source"),
                                "raw_id": req["raw_id"],
                                "classification_label": _classification_label(source_text, req["raw_id"]),
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )

                for top_id in top_ids:
                    cur.execute(
                        """
                        INSERT INTO low_level_requirement_links (
                            req_id, session_id, top_req_id, created_at
                        )
                        VALUES (%s, %s, %s, NOW())
                        ON CONFLICT DO NOTHING
                        """,
                        (req_id, DEMO_SESSION_ID, top_id),
                    )

                cur.execute(
                    """
                    INSERT INTO manage_requirements (
                        req_id, project_id, requirement_type, status, title, description,
                        priority, assignee, tags, due_date, parent_id, order_index,
                        source_req_id, source_level, custom_fields,
                        created_by, created_at, updated_by, updated_at, deleted
                    )
                    VALUES (
                        %s, %s, 'low_level', %s, %s, %s,
                        %s, NULL, %s::jsonb, NULL, %s, %s,
                        %s, 'L4', %s::jsonb,
                        'system', NOW(), 'system', NOW(), FALSE
                    )
                    """,
                    (
                        req_id,
                        project_id,
                        "draft",
                        _short_text(source_text, 260),
                        source_text,
                        _priority_for_text(source_text),
                        json.dumps(
                            ["PCA", component, _classification_label(source_text, req["raw_id"])],
                            ensure_ascii=False,
                        ),
                        primary_top_id,
                        idx,
                        req_id,
                        json.dumps(
                            {
                                "source": "low_level_requirements",
                                "raw_id": req["raw_id"],
                                "source_top_ids": top_ids,
                                "open_questions": open_questions,
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )

            graph_edge_count = 0
            for top_id, low_id in relation_pairs:
                properties = {
                    "source_kind": "structural",
                    "source_detail": "pca_demo.initial_trace_structure",
                    "source": "pca_demo.initial_trace_structure",
                    "confidence": 0.99,
                    "reason": "演示初始图谱：来自 PCA 顶层需求到底层需求的结构细化关系",
                    "evidence": [f"{top_id} -> {low_id}"],
                }
                cur.execute(
                    """
                    INSERT INTO requirement_graph_relations (
                        snapshot_id, run_id, snapshot_status, project_id, session_id, relation_mode,
                        source_node_id, target_node_id, source_req_id, target_req_id,
                        relation_type, source_kind, source_detail, weight, confidence,
                        reason, evidence, model, review_action, review_package_id,
                        properties, is_active, created_at, progress_json
                    )
                    VALUES (
                        %s, NULL, 'final', %s, %s, 'llm',
                        %s, %s, %s, %s,
                        'REFINES', 'structural', 'pca_demo.initial_trace_structure', 0.99, 0.99,
                        %s, %s::jsonb, NULL, NULL, NULL,
                        %s::jsonb, TRUE, NOW(), %s::jsonb
                    )
                    ON CONFLICT (snapshot_id, source_node_id, target_node_id, relation_type) DO NOTHING
                    """,
                    (
                        DEMO_GRAPH_INITIAL_SNAPSHOT_ID,
                        project_id,
                        DEMO_SESSION_ID,
                        f"req:{top_id}",
                        f"req:{low_id}",
                        top_id,
                        low_id,
                        properties["reason"],
                        json.dumps(properties["evidence"], ensure_ascii=False),
                        json.dumps(properties, ensure_ascii=False),
                        json.dumps(
                            {
                                "demo": "pca_requirement_graph_initial",
                                "edge_source": "top_l4_trace_structure",
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )
                graph_edge_count += cur.rowcount or 0

            cur.execute(
                """
                INSERT INTO user_project_scopes (
                    user_id, project_id, can_edit, granted_by, granted_at, updated_at
                )
                SELECT user_id, %s, TRUE, user_id, NOW(), NOW()
                FROM auth_users
                WHERE role <> 'super_admin'
                ON CONFLICT (user_id, project_id) DO UPDATE SET
                    can_edit = TRUE,
                    updated_at = NOW()
                """,
                (project_id,),
            )

            cur.execute(
                """
                INSERT INTO manage_audit_logs (
                    log_id, project_id, product_id, actor, action,
                    target_type, target_id, detail, created_at
                )
                VALUES (%s, %s, NULL, 'system', 'seed', 'pca_demo', %s, %s::jsonb, NOW())
                ON CONFLICT (log_id) DO UPDATE SET
                    project_id = EXCLUDED.project_id,
                    detail = EXCLUDED.detail,
                    created_at = NOW()
                """,
                (
                    f"seed-{DEMO_SESSION_ID}",
                    project_id,
                    DEMO_SESSION_ID,
                    json.dumps(
                        {
                            "session_id": DEMO_SESSION_ID,
                            "high_level_count": len(high_reqs),
                            "low_level_count": len(low_reqs),
                            "trace_relation_count": len(relation_pairs),
                            "graph_edge_count": graph_edge_count,
                            "meeting_meta": meeting_meta,
                            "note": "分析结果未预置，需在需求分析页点击一键分析后生成。",
                        },
                        ensure_ascii=False,
                    ),
                ),
            )

    return {
        "project_id": project_id,
        "project_name": DEMO_PROJECT_NAME,
        "session_id": DEMO_SESSION_ID,
        "high_level_count": len(high_reqs),
        "low_level_count": len(low_reqs),
        "trace_relation_count": len(relation_pairs),
        "graph_edge_count": graph_edge_count,
        "pending_issue_count": len(PENDING_ISSUES),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed PCA infusion pump demo data.")
    parser.add_argument("--md", type=Path, default=DEFAULT_MD_PATH)
    parser.add_argument("--txt", type=Path, default=DEFAULT_TXT_PATH)
    parser.add_argument("--skip-if-missing", action="store_true")
    args = parser.parse_args()

    if args.skip_if_missing and not args.md.exists():
        print(f"[seed-pca-demo] skipped; md source not found: {args.md}")
        return 0

    result = seed_demo(args.md, args.txt)
    print("[seed-pca-demo] seeded " + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
