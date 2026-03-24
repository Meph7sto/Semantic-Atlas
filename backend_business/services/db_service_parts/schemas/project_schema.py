def init_project_schema(cur):
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
    # 添加产品名称唯一约束
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'manage_products'::regclass
                  AND conname = 'uk_manage_products_name'
            ) THEN
                -- 先处理可能存在的重复名称（保留最新的）
                DELETE FROM manage_products t1
                WHERE t1.ctid < (
                    SELECT MAX(t2.ctid)
                    FROM manage_products t2
                    WHERE t1.name = t2.name
                );

                ALTER TABLE manage_products
                ADD CONSTRAINT uk_manage_products_name UNIQUE (name);
            END IF;
        END $$;
        """
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
    # 添加项目名称唯一约束
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'manage_projects'::regclass
                  AND conname = 'uk_manage_projects_name'
            ) THEN
                -- 先处理可能存在的重复名称
                DELETE FROM manage_projects t1
                WHERE t1.ctid < (
                    SELECT MAX(t2.ctid)
                    FROM manage_projects t2
                    WHERE t1.name = t2.name
                );

                ALTER TABLE manage_projects
                ADD CONSTRAINT uk_manage_projects_name UNIQUE (name);
            END IF;
        END $$;
        """
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
        CREATE TABLE IF NOT EXISTS manage_defects (
            defect_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES manage_projects(project_id) ON DELETE CASCADE,
            requirement_id TEXT NOT NULL REFERENCES manage_requirements(req_id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            reproduce_steps TEXT NOT NULL DEFAULT '',
            severity TEXT NOT NULL DEFAULT 'medium' CHECK (severity IN ('critical', 'high', 'medium', 'low')),
            priority TEXT NOT NULL DEFAULT 'P2' CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
            status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved', 'verified', 'closed', 'rejected')),
            reporter TEXT,
            dev_assignee TEXT,
            tester_assignee TEXT,
            current_assignee TEXT,
            created_by TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_by TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_manage_defects_project ON manage_defects(project_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_manage_defects_requirement ON manage_defects(requirement_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_manage_defects_status ON manage_defects(status)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_manage_defects_current_assignee ON manage_defects(current_assignee)"
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
