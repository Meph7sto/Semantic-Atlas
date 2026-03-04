def init_auth_user_schema(cur):
    # ========================
    # Authentication: Users Table (用户认证表)
    # ========================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_users (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('super_admin', 'admin', 'member', 'viewer')),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        DO $$
        DECLARE
            old_constraint_name TEXT;
        BEGIN
            SELECT conname
              INTO old_constraint_name
              FROM pg_constraint
             WHERE conrelid = 'auth_users'::regclass
               AND contype = 'c'
               AND pg_get_constraintdef(oid) LIKE '%role%'
               AND pg_get_constraintdef(oid) LIKE '%admin%'
               AND conname <> 'chk_auth_users_role'
             LIMIT 1;

            IF old_constraint_name IS NOT NULL THEN
                EXECUTE format('ALTER TABLE auth_users DROP CONSTRAINT %I', old_constraint_name);
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'auth_users'::regclass
                  AND conname = 'chk_auth_users_role'
            ) THEN
                ALTER TABLE auth_users
                ADD CONSTRAINT chk_auth_users_role
                CHECK (role IN ('super_admin', 'admin', 'member', 'viewer'));
            END IF;
        END $$;
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_users_username ON auth_users(username)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_users_role ON auth_users(role)"
    )

    # 初始化测试用户（仅在用户表为空时插入）
    cur.execute(
        """
        INSERT INTO auth_users (user_id, username, password_hash, display_name, role, is_active)
        VALUES ('test-user-001', 'test', '$2b$12$6m.Xy3YEOvHNSXvq79T/meEpiTFFOOYVaR2aEp8pbFlfqsr/XkLki', '测试用户 (全权限)', 'super_admin', TRUE)
        ON CONFLICT (user_id) DO NOTHING
        """
    )
    # 强制更新测试用户为 super_admin 角色，拥有所有权限
    cur.execute(
        """
        UPDATE auth_users
        SET username = 'test',
            password_hash = '$2b$12$6m.Xy3YEOvHNSXvq79T/meEpiTFFOOYVaR2aEp8pbFlfqsr/XkLki',
            role = 'super_admin',
            display_name = '测试用户 (全权限)',
            updated_at = NOW()
        WHERE user_id = 'test-user-001'
        """
    )
    # 硬编码超级管理员：admin / admin
    cur.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM auth_users WHERE username = 'admin'
            ) THEN
                UPDATE auth_users
                SET password_hash = '$2b$12$JaZlrZRNkzxUa3yWzGsL.OqgApgiD60JvaeChZVz2M5blTMH40Aly',
                    role = 'super_admin',
                    display_name = '系统超级管理员',
                    is_active = TRUE,
                    updated_at = NOW()
                WHERE username = 'admin';
            ELSIF EXISTS (
                SELECT 1 FROM auth_users WHERE user_id = 'super-admin-001'
            ) THEN
                UPDATE auth_users
                SET username = 'admin',
                    password_hash = '$2b$12$JaZlrZRNkzxUa3yWzGsL.OqgApgiD60JvaeChZVz2M5blTMH40Aly',
                    role = 'super_admin',
                    display_name = '系统超级管理员',
                    is_active = TRUE,
                    updated_at = NOW()
                WHERE user_id = 'super-admin-001';
            ELSE
                INSERT INTO auth_users (user_id, username, password_hash, display_name, role, is_active)
                VALUES (
                    'super-admin-001',
                    'admin',
                    '$2b$12$JaZlrZRNkzxUa3yWzGsL.OqgApgiD60JvaeChZVz2M5blTMH40Aly',
                    '系统超级管理员',
                    'super_admin',
                    TRUE
                );
            END IF;
        END $$;
        """
    )
    # 将历史 admin 自动迁移为 super_admin（保持历史行为）
    cur.execute(
        """
        UPDATE auth_users
        SET role = 'super_admin',
            updated_at = NOW()
        WHERE role = 'admin'
        """
    )

    # ========================
    # Permission System: Schema Changes
    # ========================

    # 1.1 添加 external_type 到 auth_users 表（外部身份标识）
    cur.execute(
        """
        ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS external_type TEXT
        """
    )

    # 1.1.1 添加 avatar_url 到 auth_users 表（用户头像 URL）
    cur.execute(
        """
        ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS avatar_url TEXT
        """
    )

    # ========================
    # Registration Approval Workflow: 注册审批流程字段
    # ========================

    # 1.2 添加 registration_status 字段（注册状态）
    cur.execute(
        """
        ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS registration_status TEXT
        """
    )
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'auth_users'::regclass
                  AND conname = 'chk_auth_users_registration_status'
            ) THEN
                ALTER TABLE auth_users
                ADD CONSTRAINT chk_auth_users_registration_status
                CHECK (registration_status IN ('pending', 'approved', 'rejected'));
            END IF;
        END $$;
        """
    )

    # 1.3 添加 rejection_reason 字段（拒绝原因）
    cur.execute(
        """
        ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS rejection_reason TEXT
        """
    )

    # 1.4 添加 rejected_at 字段（拒绝时间）
    cur.execute(
        """
        ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMPTZ
        """
    )

    # 1.5 添加 approved_at 字段（批准时间）
    cur.execute(
        """
        ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ
        """
    )

    # 1.6 添加 approved_by 字段（批准人）
    cur.execute(
        """
        ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS approved_by TEXT
        """
    )

    # 1.7 添加 rejected_by 字段（拒绝人）
    cur.execute(
        """
        ALTER TABLE auth_users ADD COLUMN IF NOT EXISTS rejected_by TEXT
        """
    )

    # 1.8 添加索引（按注册状态查询）
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_users_registration_status ON auth_users(registration_status)"
    )

    # 1.9 迁移现有用户为已批准状态
    cur.execute(
        """
        UPDATE auth_users
        SET registration_status = 'approved',
            approved_at = created_at,
            approved_by = user_id
        WHERE registration_status IS NULL AND is_active = TRUE
        """
    )
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'auth_users'::regclass
                  AND conname = 'chk_auth_users_external_type'
            ) THEN
                ALTER TABLE auth_users
                ADD CONSTRAINT chk_auth_users_external_type
                CHECK (external_type IS NULL OR external_type IN ('CLIENT', 'CONTRACTOR'));
            END IF;
        END $$;
        """
    )

    # 1.2 添加优先级相关字段到 manage_requirements 表
    cur.execute(
        """
        ALTER TABLE manage_requirements
        ADD COLUMN IF NOT EXISTS priority_suggested INTEGER
        """
    )
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'manage_requirements'::regclass
                  AND conname = 'chk_manage_requirements_priority_suggested'
            ) THEN
                ALTER TABLE manage_requirements
                ADD CONSTRAINT chk_manage_requirements_priority_suggested
                CHECK (priority_suggested IS NULL OR (priority_suggested >= 1 AND priority_suggested <= 5));
            END IF;
        END $$;
        """
    )
    cur.execute(
        """
        ALTER TABLE manage_requirements
        ADD COLUMN IF NOT EXISTS priority_final INTEGER
        """
    )
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'manage_requirements'::regclass
                  AND conname = 'chk_manage_requirements_priority_final'
            ) THEN
                ALTER TABLE manage_requirements
                ADD CONSTRAINT chk_manage_requirements_priority_final
                CHECK (priority_final IS NULL OR (priority_final >= 1 AND priority_final <= 5));
            END IF;
        END $$;
        """
    )
    cur.execute(
        """
        ALTER TABLE manage_requirements
        ADD COLUMN IF NOT EXISTS priority_decided_by TEXT
        """
    )
    cur.execute(
        """
        ALTER TABLE manage_requirements
        ADD COLUMN IF NOT EXISTS priority_decided_at TIMESTAMPTZ
        """
    )
    cur.execute(
        """
        ALTER TABLE manage_requirements
        ADD COLUMN IF NOT EXISTS baseline_id BIGINT
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_manage_requirements_baseline ON manage_requirements(baseline_id)"
    )

    # 1.3 项目成员表：记录谁在哪个项目
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS project_members (
            id BIGSERIAL PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES manage_projects(project_id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
            joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(project_id, user_id)
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_members_project ON project_members(project_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_members_user ON project_members(user_id)"
    )

    # 1.4 成员角色表：支持一个成员拥有多个角色
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS member_roles (
            id BIGSERIAL PRIMARY KEY,
            member_id BIGINT NOT NULL REFERENCES project_members(id) ON DELETE CASCADE,
            role_id TEXT NOT NULL CHECK (role_id IN ('PO', 'BA', 'DEV', 'REVIEWER', 'QA', 'CONTRACTOR', 'CLIENT')),
            granted_by TEXT NOT NULL REFERENCES auth_users(user_id),
            granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(member_id, role_id)
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_member_roles_member ON member_roles(member_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_member_roles_role ON member_roles(role_id)"
    )

    # 1.5 评审指派表：记录需求的评审实例
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS review_assignments (
            id BIGSERIAL PRIMARY KEY,
            requirement_id TEXT NOT NULL REFERENCES manage_requirements(req_id) ON DELETE CASCADE,
            reviewer_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
            initiated_by TEXT NOT NULL REFERENCES auth_users(user_id),
            seq SMALLINT NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'WITHDRAWN')),
            comment TEXT,
            decided_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_review_assignments_req ON review_assignments(requirement_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_review_assignments_reviewer ON review_assignments(reviewer_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_review_assignments_status ON review_assignments(status)"
    )

    # 1.6 基线表：记录项目基线版本
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS baselines (
            id BIGSERIAL PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES manage_projects(project_id) ON DELETE CASCADE,
            version TEXT NOT NULL CHECK (char_length(version) >= 1),
            locked BOOLEAN NOT NULL DEFAULT FALSE,
            created_by TEXT NOT NULL REFERENCES auth_users(user_id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_baselines_project ON baselines(project_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_baselines_version ON baselines(project_id, version)"
    )

    # 1.7 变更请求表：记录需求变更申请
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS change_requests (
            id BIGSERIAL PRIMARY KEY,
            requirement_id TEXT NOT NULL REFERENCES manage_requirements(req_id) ON DELETE CASCADE,
            baseline_id BIGINT NOT NULL REFERENCES baselines(id) ON DELETE RESTRICT,
            requested_by TEXT NOT NULL REFERENCES auth_users(user_id),
            reason TEXT NOT NULL CHECK (char_length(reason) >= 1),
            change_summary TEXT NOT NULL CHECK (char_length(change_summary) >= 1),
            status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
            reviewed_by TEXT REFERENCES auth_users(user_id),
            review_comment TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMPTZ
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_change_requests_req ON change_requests(requirement_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_change_requests_baseline ON change_requests(baseline_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_change_requests_status ON change_requests(status)"
    )

    # 1.9 用户可见范围：产品级授权
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_product_scopes (
            id BIGSERIAL PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
            product_id TEXT NOT NULL REFERENCES manage_products(product_id) ON DELETE CASCADE,
            can_edit BOOLEAN NOT NULL DEFAULT FALSE,
            granted_by TEXT NOT NULL REFERENCES auth_users(user_id),
            granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, product_id)
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_product_scopes_user ON user_product_scopes(user_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_product_scopes_product ON user_product_scopes(product_id)"
    )

    # 1.10 用户可见范围：项目级授权
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_project_scopes (
            id BIGSERIAL PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES auth_users(user_id) ON DELETE CASCADE,
            project_id TEXT NOT NULL REFERENCES manage_projects(project_id) ON DELETE CASCADE,
            can_edit BOOLEAN NOT NULL DEFAULT FALSE,
            granted_by TEXT NOT NULL REFERENCES auth_users(user_id),
            granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, project_id)
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_project_scopes_user ON user_project_scopes(user_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_project_scopes_project ON user_project_scopes(project_id)"
    )

    # 1.11 历史用户默认全量可见且可编辑（非 super_admin）
    cur.execute(
        """
        INSERT INTO user_product_scopes (user_id, product_id, can_edit, granted_by, granted_at, updated_at)
        SELECT u.user_id, p.product_id, TRUE, u.user_id, NOW(), NOW()
        FROM auth_users u
        CROSS JOIN manage_products p
        WHERE u.role <> 'super_admin'
        ON CONFLICT (user_id, product_id) DO NOTHING
        """
    )
    cur.execute(
        """
        INSERT INTO user_project_scopes (user_id, project_id, can_edit, granted_by, granted_at, updated_at)
        SELECT u.user_id, p.project_id, TRUE, u.user_id, NOW(), NOW()
        FROM auth_users u
        CROSS JOIN manage_projects p
        WHERE u.role <> 'super_admin'
        ON CONFLICT (user_id, project_id) DO NOTHING
        """
    )

    # 1.8 添加基线外键约束（在 baselines 表创建后）
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'manage_requirements'::regclass
                  AND conname = 'fk_manage_requirements_baseline'
            ) THEN
                ALTER TABLE manage_requirements
                ADD CONSTRAINT fk_manage_requirements_baseline
                FOREIGN KEY (baseline_id) REFERENCES baselines(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
