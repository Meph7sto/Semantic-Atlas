def init_requirement_schema(cur):
    # ========================
    # Phase 3: Requirements L123 Table
    # ========================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS requirements_l123 (
            req_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            level TEXT NOT NULL CHECK (level IN ('L1', 'L2', 'L3')),
            text TEXT NOT NULL CHECK (char_length(text) >= 10 AND char_length(text) <= 500),
            fingerprint TEXT NOT NULL UNIQUE,
            anchor_span_id TEXT REFERENCES spans(span_id) ON DELETE CASCADE,
            r INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_requirements_l123_session ON requirements_l123(session_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_requirements_l123_level ON requirements_l123(level)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_requirements_l123_fingerprint ON requirements_l123(fingerprint)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_requirements_l123_anchor_span ON requirements_l123(anchor_span_id)"
    )

    # ========================
    # Low-level Requirements Table (L4 底层需求表)
    # ========================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS low_level_requirements (
            req_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            source_top_id TEXT,
            source_top_text TEXT,
            text TEXT NOT NULL,
            component TEXT,
            acceptance_criteria JSONB,
            test_method TEXT,
            interfaces JSONB,
            data_contracts JSONB,
            error_handling JSONB,
            nfr JSONB,
            open_questions JSONB,
            evidence_ids JSONB,
            confidence REAL,
            source TEXT,
            meta JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # 扩展旧表字段（必须先补齐字段，再建索引）
    cur.execute(
        "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS source_top_id TEXT"
    )
    cur.execute(
        "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS source_top_text TEXT"
    )
    cur.execute(
        "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS component TEXT"
    )
    cur.execute(
        "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS acceptance_criteria JSONB"
    )
    cur.execute(
        "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS test_method TEXT"
    )
    cur.execute(
        "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS interfaces JSONB"
    )
    cur.execute(
        "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS data_contracts JSONB"
    )
    cur.execute(
        "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS error_handling JSONB"
    )
    cur.execute(
        "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS nfr JSONB"
    )
    cur.execute(
        "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS open_questions JSONB"
    )
    cur.execute(
        "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS evidence_ids JSONB"
    )
    cur.execute(
        "ALTER TABLE low_level_requirements ADD COLUMN IF NOT EXISTS confidence REAL"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_low_level_requirements_session ON low_level_requirements(session_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_low_level_requirements_source_top ON low_level_requirements(source_top_id)"
    )

    # ========================
    # Low-level to Top Requirements Mapping (多对多映射表)
    # ========================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS low_level_requirement_links (
            req_id TEXT NOT NULL REFERENCES low_level_requirements(req_id) ON DELETE CASCADE,
            session_id TEXT NOT NULL,
            top_req_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (req_id, top_req_id)
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_low_level_requirement_links_session ON low_level_requirement_links(session_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_low_level_requirement_links_top ON low_level_requirement_links(top_req_id)"
    )

    # ========================
    # Conflict Analysis Table (冲突检测结果表)
    # ========================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS conflict_analysis (
            id SERIAL PRIMARY KEY,
            batch_id TEXT,
            session_id TEXT,
            requirement_a TEXT NOT NULL,
            requirement_b TEXT NOT NULL,
            is_conflict BOOLEAN NOT NULL,
            raw_response TEXT,
            result_json JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "ALTER TABLE conflict_analysis ADD COLUMN IF NOT EXISTS batch_id TEXT"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_conflict_analysis_session ON conflict_analysis(session_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_conflict_analysis_batch ON conflict_analysis(batch_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_conflict_analysis_created_at ON conflict_analysis(created_at)"
    )

    # ========================
    # Classification Analysis Table (需求分类结果表)
    # ========================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS classification_analysis (
            id SERIAL PRIMARY KEY,
            session_id TEXT,
            requirements JSONB NOT NULL,
            predictions JSONB NOT NULL,
            label_distribution JSONB,
            total INTEGER,
            result_json JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_classification_analysis_session ON classification_analysis(session_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_classification_analysis_created_at ON classification_analysis(created_at)"
    )

    # ========================
    # Requirement Graph Relations Snapshot Table
    # ========================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS requirement_graph_relations (
            id BIGSERIAL PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            project_id TEXT,
            session_id TEXT,
            relation_mode TEXT NOT NULL,
            source_node_id TEXT NOT NULL,
            target_node_id TEXT NOT NULL,
            source_req_id TEXT NOT NULL,
            target_req_id TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            source_detail TEXT,
            weight REAL NOT NULL DEFAULT 0,
            confidence REAL,
            reason TEXT,
            evidence JSONB,
            model TEXT,
            review_action TEXT,
            review_package_id TEXT,
            properties JSONB,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            invalidated_at TIMESTAMPTZ,
            UNIQUE (snapshot_id, source_node_id, target_node_id, relation_type)
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_requirement_graph_relations_snapshot ON requirement_graph_relations(snapshot_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_requirement_graph_relations_lookup ON requirement_graph_relations(project_id, session_id, relation_mode, is_active)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_requirement_graph_relations_source_req ON requirement_graph_relations(source_req_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_requirement_graph_relations_target_req ON requirement_graph_relations(target_req_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_requirement_graph_relations_type ON requirement_graph_relations(relation_type)"
    )
