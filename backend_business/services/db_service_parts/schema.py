def init_db(conn):
    with conn.cursor() as cur:
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
        # Requirements Management (Monitor)
        # ========================

        # ========================
        # Product Layer (产品薄层)
        # ========================
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS manage_products (
                product_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
                roadmap TEXT,
                version TEXT,
                tags JSONB,
                created_by TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_products_status ON manage_products(status)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_products_created_at ON manage_products(created_at)"
        )

        # 产品成员表（可选：用于产品级别角色管理）
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS manage_product_members (
                id SERIAL PRIMARY KEY,
                product_id TEXT NOT NULL REFERENCES manage_products(product_id) ON DELETE CASCADE,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(product_id, user_id)
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_product_members_product ON manage_product_members(product_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_product_members_user ON manage_product_members(user_id)"
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS manage_projects (
                project_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
                product_id TEXT REFERENCES manage_products(product_id) ON DELETE SET NULL,
                created_by TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        # 为已有表添加 product_id 列（兼容旧数据）
        cur.execute(
            "ALTER TABLE manage_projects ADD COLUMN IF NOT EXISTS product_id TEXT REFERENCES manage_products(product_id) ON DELETE SET NULL"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_projects_product ON manage_projects(product_id)"
        )
        # 项目-Session 绑定：记录当前关联的采集 session_id
        cur.execute(
            "ALTER TABLE manage_projects ADD COLUMN IF NOT EXISTS current_session_id TEXT"
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS manage_requirements (
                req_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES manage_projects(project_id) ON DELETE CASCADE,
                requirement_type TEXT NOT NULL CHECK (requirement_type IN ('top_level', 'low_level', 'task')),
                status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'under_review', 'confirmed', 'in_progress', 'completed', 'archived')),
                title TEXT NOT NULL,
                description TEXT,
                priority TEXT,
                assignee TEXT,
                tags JSONB,
                due_date TEXT,
                parent_id TEXT REFERENCES manage_requirements(req_id) ON DELETE SET NULL,
                order_index INTEGER NOT NULL DEFAULT 0,
                source_req_id TEXT,
                source_level TEXT,
                custom_fields JSONB,
                created_by TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_by TEXT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                deleted BOOLEAN NOT NULL DEFAULT FALSE,
                is_planned BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
        cur.execute(
            "ALTER TABLE manage_requirements ADD COLUMN IF NOT EXISTS is_planned BOOLEAN NOT NULL DEFAULT FALSE"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_requirements_project ON manage_requirements(project_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_requirements_parent ON manage_requirements(parent_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_requirements_type ON manage_requirements(requirement_type)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_requirements_status ON manage_requirements(status)"
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS manage_test_cases (
                test_case_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES manage_projects(project_id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'deprecated')),
                source TEXT,
                created_by TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_test_cases_project ON manage_test_cases(project_id)"
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS manage_requirement_test_links (
                link_id SERIAL PRIMARY KEY,
                requirement_id TEXT NOT NULL REFERENCES manage_requirements(req_id) ON DELETE CASCADE,
                test_case_id TEXT NOT NULL REFERENCES manage_test_cases(test_case_id) ON DELETE CASCADE,
                link_type TEXT NOT NULL DEFAULT 'verification',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(requirement_id, test_case_id)
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS manage_milestones (
                milestone_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES manage_projects(project_id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT,
                message TEXT,
                milestone_type TEXT NOT NULL DEFAULT 'regular' CHECK (milestone_type IN ('regular', 'baseline', 'branch', 'merge')),
                is_baseline BOOLEAN NOT NULL DEFAULT FALSE,
                sprint TEXT,
                version TEXT,
                tags JSONB,
                created_by TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                metadata JSONB
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_milestones_project ON manage_milestones(project_id)"
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS manage_milestone_nodes (
                snapshot_id TEXT PRIMARY KEY,
                milestone_id TEXT NOT NULL REFERENCES manage_milestones(milestone_id) ON DELETE CASCADE,
                requirement_id TEXT NOT NULL,
                requirement_type TEXT,
                status TEXT,
                title TEXT,
                description TEXT,
                parent_id TEXT,
                order_index INTEGER,
                snapshot_data JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_milestone_nodes_milestone ON manage_milestone_nodes(milestone_id)"
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS manage_milestone_relations (
                id SERIAL PRIMARY KEY,
                milestone_id TEXT NOT NULL REFERENCES manage_milestones(milestone_id) ON DELETE CASCADE,
                parent_id TEXT NOT NULL,
                child_id TEXT NOT NULL,
                order_index INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_milestone_relations_milestone ON manage_milestone_relations(milestone_id)"
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS manage_milestone_edges (
                id SERIAL PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES manage_projects(project_id) ON DELETE CASCADE,
                from_milestone_id TEXT NOT NULL REFERENCES manage_milestones(milestone_id) ON DELETE CASCADE,
                to_milestone_id TEXT NOT NULL REFERENCES manage_milestones(milestone_id) ON DELETE CASCADE,
                relation_type TEXT NOT NULL,
                message TEXT,
                created_by TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_milestone_edges_project ON manage_milestone_edges(project_id)"
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS manage_branch_refs (
                ref_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES manage_projects(project_id) ON DELETE CASCADE,
                ref_name TEXT NOT NULL,
                ref_type TEXT NOT NULL DEFAULT 'branch' CHECK (ref_type IN ('branch', 'tag')),
                milestone_id TEXT REFERENCES manage_milestones(milestone_id) ON DELETE SET NULL,
                created_by TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(project_id, ref_name)
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_branch_refs_project ON manage_branch_refs(project_id)"
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS manage_branches (
                branch_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES manage_projects(project_id) ON DELETE CASCADE,
                base_milestone_id TEXT NOT NULL REFERENCES manage_milestones(milestone_id) ON DELETE RESTRICT,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'under_review', 'merged', 'closed')),
                created_by TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                metadata JSONB
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_branches_project ON manage_branches(project_id)"
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS manage_change_sets (
                change_id TEXT PRIMARY KEY,
                branch_id TEXT NOT NULL REFERENCES manage_branches(branch_id) ON DELETE CASCADE,
                change_type TEXT NOT NULL CHECK (change_type IN ('added', 'modified', 'deleted', 'moved')),
                requirement_id TEXT,
                before_data JSONB,
                after_data JSONB,
                created_by TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_change_sets_branch ON manage_change_sets(branch_id)"
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS manage_impact_reports (
                report_id TEXT PRIMARY KEY,
                branch_id TEXT NOT NULL REFERENCES manage_branches(branch_id) ON DELETE CASCADE,
                summary TEXT,
                detail_json JSONB,
                status TEXT NOT NULL DEFAULT 'pending',
                created_by TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_impact_reports_branch ON manage_impact_reports(branch_id)"
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS manage_merge_logs (
                merge_id TEXT PRIMARY KEY,
                branch_id TEXT NOT NULL REFERENCES manage_branches(branch_id) ON DELETE CASCADE,
                target_milestone_id TEXT REFERENCES manage_milestones(milestone_id) ON DELETE SET NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'conflicts', 'merged', 'failed')),
                summary TEXT,
                created_by TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_merge_logs_branch ON manage_merge_logs(branch_id)"
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS manage_reviews (
                review_id TEXT PRIMARY KEY,
                branch_id TEXT NOT NULL REFERENCES manage_branches(branch_id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'changes_requested')),
                reviewer TEXT,
                comment TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_reviews_branch ON manage_reviews(branch_id)"
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS manage_audit_logs (
                log_id TEXT PRIMARY KEY,
                project_id TEXT,
                product_id TEXT,
                actor TEXT,
                action TEXT,
                target_type TEXT,
                target_id TEXT,
                detail JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        # 兼容旧部署：为已存在的审计表补齐 product_id 字段
        cur.execute(
            "ALTER TABLE manage_audit_logs ADD COLUMN IF NOT EXISTS product_id TEXT"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_audit_logs_project ON manage_audit_logs(project_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_manage_audit_logs_product ON manage_audit_logs(product_id)"
        )

        # 兼容旧数据：此前产品审计误用 project_id 字段存放 product_id
        cur.execute(
            """
            UPDATE manage_audit_logs
            SET product_id = project_id,
                project_id = NULL
            WHERE product_id IS NULL
              AND project_id IS NOT NULL
              AND (
                target_type IN ('product', 'product_member')
                OR target_type LIKE 'product%'
              )
            """
        )

        # ========================
        # Push Messages Table (实时消息推送)
        # ========================
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS push_messages (
                message_id TEXT PRIMARY KEY,
                message_type TEXT NOT NULL CHECK (message_type IN ('review', 'change')),
                title TEXT NOT NULL,
                content TEXT,
                source TEXT,
                priority TEXT DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high')),
                ai_suggestion TEXT,
                metadata JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                read BOOLEAN NOT NULL DEFAULT FALSE,
                pushed BOOLEAN NOT NULL DEFAULT FALSE,
                pushed_at TIMESTAMPTZ
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_push_messages_type ON push_messages(message_type)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_push_messages_pushed ON push_messages(pushed)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_push_messages_created_at ON push_messages(created_at)"
        )

        # ========================
        # Mobile Chat Messages Table (移动端对话桥接)
        # ========================
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS mobile_chat_messages (
                message_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                sender TEXT NOT NULL CHECK (sender IN ('web', 'mobile')),
                content TEXT NOT NULL,
                metadata JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_mobile_chat_session ON mobile_chat_messages(session_id)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_mobile_chat_created_at ON mobile_chat_messages(created_at)"
        )
