def init_trace_schema(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS trace_analysis (
            id SERIAL PRIMARY KEY,
            session_id TEXT,
            analysis_type TEXT NOT NULL,              -- relation | batch
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            input_json TEXT NOT NULL,
            output_json TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "ALTER TABLE trace_analysis ADD COLUMN IF NOT EXISTS session_id TEXT"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_trace_created_at ON trace_analysis(created_at)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_trace_session_id ON trace_analysis(session_id)"
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS spans (
            span_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            start_ms INTEGER,
            end_ms INTEGER,
            speaker TEXT,
            text TEXT NOT NULL,
            asr_confidence REAL,
            meta_json TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "ALTER TABLE spans ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
    )
    cur.execute(
        "ALTER TABLE spans ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_spans_session_id ON spans(session_id)"
    )

    # ========================
    # Phase 2 Tables
    # ========================

    # context_runs: 记录一次 Phase2 运行
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS context_runs (
            context_run_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            options_snapshot JSONB,
            status TEXT NOT NULL DEFAULT 'RUNNING',
            stats JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_context_runs_session_id ON context_runs(session_id)"
    )

    # span_links: 稀疏关联矩阵（边表）
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS span_links (
            id SERIAL PRIMARY KEY,
            context_run_id TEXT NOT NULL REFERENCES context_runs(context_run_id) ON DELETE CASCADE,
            source_span_id TEXT NOT NULL REFERENCES spans(span_id) ON DELETE CASCADE,
            target_span_id TEXT NOT NULL REFERENCES spans(span_id) ON DELETE CASCADE,
            relation_type TEXT NOT NULL CHECK (relation_type IN ('continuation', 'elaboration', 'dependency', 'same_topic', 'conflict')),
            strength REAL NOT NULL CHECK (strength >= 0 AND strength <= 1),
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(context_run_id, source_span_id, target_span_id, relation_type)
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_span_links_context_run ON span_links(context_run_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_span_links_source ON span_links(source_span_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_span_links_target ON span_links(target_span_id)"
    )

    # bundles: 上下文包
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bundles (
            bundle_id TEXT PRIMARY KEY,
            context_run_id TEXT NOT NULL REFERENCES context_runs(context_run_id) ON DELETE CASCADE,
            session_id TEXT NOT NULL,
            order_index INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'READY',
            context_summary TEXT,
            meta JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute("ALTER TABLE bundles ADD COLUMN IF NOT EXISTS context_run_id TEXT")
    cur.execute("ALTER TABLE bundles ADD COLUMN IF NOT EXISTS session_id TEXT")
    cur.execute("ALTER TABLE bundles ADD COLUMN IF NOT EXISTS order_index INTEGER")
    cur.execute("ALTER TABLE bundles ADD COLUMN IF NOT EXISTS status TEXT")
    cur.execute("ALTER TABLE bundles ADD COLUMN IF NOT EXISTS context_summary TEXT")
    cur.execute("ALTER TABLE bundles ADD COLUMN IF NOT EXISTS meta JSONB")
    cur.execute(
        "ALTER TABLE bundles ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
    )
    cur.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'bundles'
                  AND column_name = 'bundle_type'
                  AND is_nullable = 'NO'
            ) THEN
                ALTER TABLE bundles
                    ALTER COLUMN bundle_type DROP NOT NULL;
            END IF;
        END $$;
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_bundles_context_run ON bundles(context_run_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_bundles_session_id ON bundles(session_id)"
    )

    # bundle_items: bundle 内 span 映射
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bundle_items (
            id SERIAL PRIMARY KEY,
            bundle_id TEXT NOT NULL REFERENCES bundles(bundle_id) ON DELETE CASCADE,
            span_id TEXT NOT NULL REFERENCES spans(span_id) ON DELETE CASCADE,
            span_ref TEXT NOT NULL,
            order_index INTEGER NOT NULL,
            UNIQUE(bundle_id, span_ref),
            UNIQUE(bundle_id, span_id)
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_bundle_items_bundle ON bundle_items(bundle_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_bundle_items_span ON bundle_items(span_id)"
    )

    # 兼容旧表结构：补齐 spans 外键
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_attribute a
                    ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                WHERE c.conrelid = 'span_links'::regclass
                  AND c.contype = 'f'
                  AND a.attname = 'source_span_id'
            ) THEN
                ALTER TABLE span_links
                    ADD CONSTRAINT fk_span_links_source_span
                    FOREIGN KEY (source_span_id) REFERENCES spans(span_id) ON DELETE CASCADE;
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_attribute a
                    ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                WHERE c.conrelid = 'span_links'::regclass
                  AND c.contype = 'f'
                  AND a.attname = 'target_span_id'
            ) THEN
                ALTER TABLE span_links
                    ADD CONSTRAINT fk_span_links_target_span
                    FOREIGN KEY (target_span_id) REFERENCES spans(span_id) ON DELETE CASCADE;
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_attribute a
                    ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                WHERE c.conrelid = 'bundle_items'::regclass
                  AND c.contype = 'f'
                  AND a.attname = 'span_id'
            ) THEN
                ALTER TABLE bundle_items
                    ADD CONSTRAINT fk_bundle_items_span
                    FOREIGN KEY (span_id) REFERENCES spans(span_id) ON DELETE CASCADE;
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_attribute a
                    ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                WHERE c.conrelid = 'bundles'::regclass
                  AND c.contype = 'f'
                  AND a.attname = 'context_run_id'
            ) THEN
                ALTER TABLE bundles
                    ADD CONSTRAINT fk_bundles_context_run
                    FOREIGN KEY (context_run_id) REFERENCES context_runs(context_run_id) ON DELETE CASCADE;
            END IF;
        END $$;
        """
    )
