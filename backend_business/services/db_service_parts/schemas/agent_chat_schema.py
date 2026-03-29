def init_agent_chat_schema(cur):
    # ========================
    # AI Chat Sessions / Messages
    # ========================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_chat_sessions (
            session_id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES manage_projects(project_id) ON DELETE SET NULL,
            user_id TEXT NOT NULL,
            title TEXT,
            active_graph_id TEXT,
            agent_type TEXT NOT NULL DEFAULT 'requirement_agent',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "ALTER TABLE ai_chat_sessions ADD COLUMN IF NOT EXISTS active_graph_id TEXT"
    )
    cur.execute(
        "ALTER TABLE ai_chat_sessions ADD COLUMN IF NOT EXISTS agent_type TEXT"
    )
    cur.execute(
        "UPDATE ai_chat_sessions SET agent_type = 'requirement_agent' WHERE agent_type IS NULL OR agent_type = ''"
    )
    cur.execute(
        "ALTER TABLE ai_chat_sessions ALTER COLUMN agent_type SET DEFAULT 'requirement_agent'"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_chat_sessions_user_project ON ai_chat_sessions(user_id, project_id, updated_at DESC)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_chat_sessions_agent_type ON ai_chat_sessions(agent_type)"
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_chat_messages (
            message_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES ai_chat_sessions(session_id) ON DELETE CASCADE,
            user_id TEXT,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            metadata JSONB,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_chat_messages_session_created ON ai_chat_messages(session_id, created_at)"
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
    # Requirement Change Approval Requests (Agent 审批挂起)
    # ========================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS requirement_change_approvals (
            approval_request_id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES manage_projects(project_id) ON DELETE CASCADE,
            session_id TEXT REFERENCES ai_chat_sessions(session_id) ON DELETE SET NULL,
            graph_id TEXT,
            requirement_id TEXT NOT NULL,
            requested_by TEXT NOT NULL,
            source_agent TEXT NOT NULL DEFAULT 'requirement_agent',
            approval_type TEXT NOT NULL DEFAULT 'requirement_update',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'rejected', 'applied')),
            updates_json JSONB NOT NULL,
            summary_text TEXT,
            push_message_id TEXT REFERENCES push_messages(message_id) ON DELETE SET NULL,
            approved_by TEXT,
            rejected_by TEXT,
            decision_comment TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMPTZ,
            applied_at TIMESTAMPTZ
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_requirement_change_approvals_status ON requirement_change_approvals(status)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_requirement_change_approvals_session ON requirement_change_approvals(session_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_requirement_change_approvals_push_message ON requirement_change_approvals(push_message_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_requirement_change_approvals_requirement ON requirement_change_approvals(requirement_id)"
    )

    # ========================
    # Mobile Chat Messages Table (移动端对话桥接)
    # ========================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS mobile_chat_messages (
            message_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT 'anonymous',
            session_id TEXT NOT NULL,
            sender TEXT NOT NULL CHECK (sender IN ('web', 'mobile')),
            content TEXT NOT NULL,
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "ALTER TABLE mobile_chat_messages ADD COLUMN IF NOT EXISTS user_id TEXT"
    )
    cur.execute(
        "UPDATE mobile_chat_messages SET user_id = 'anonymous' WHERE user_id IS NULL OR user_id = ''"
    )
    cur.execute(
        "ALTER TABLE mobile_chat_messages ALTER COLUMN user_id SET DEFAULT 'anonymous'"
    )
    cur.execute(
        "ALTER TABLE mobile_chat_messages ALTER COLUMN user_id SET NOT NULL"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_mobile_chat_session ON mobile_chat_messages(session_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_mobile_chat_user_session_created ON mobile_chat_messages(user_id, session_id, created_at)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_mobile_chat_created_at ON mobile_chat_messages(created_at)"
    )

    # ========================
    # Agent Communication Tables (多 Agent 通信持久化)
    # ========================

    # 通信通道
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_channels (
            channel_id    TEXT PRIMARY KEY,
            channel_type  TEXT NOT NULL CHECK (channel_type IN ('direct','group','broadcast')),
            name          TEXT,
            project_id    TEXT REFERENCES manage_projects(project_id) ON DELETE SET NULL,
            created_by    TEXT NOT NULL,
            created_at    TIMESTAMPTZ DEFAULT NOW(),
            is_archived   BOOLEAN DEFAULT FALSE
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_channels_project ON agent_channels(project_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_channels_type ON agent_channels(channel_type)"
    )

    # 通道成员
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_channel_members (
            channel_id  TEXT NOT NULL REFERENCES agent_channels(channel_id) ON DELETE CASCADE,
            agent_id    TEXT NOT NULL,
            role        TEXT DEFAULT 'member',
            joined_at   TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (channel_id, agent_id)
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_channel_members_agent ON agent_channel_members(agent_id)"
    )

    # Agent 消息记录
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_messages (
            message_id   TEXT PRIMARY KEY,
            channel_id   TEXT NOT NULL REFERENCES agent_channels(channel_id) ON DELETE CASCADE,
            sender_id    TEXT NOT NULL,
            message_type TEXT NOT NULL CHECK (message_type IN ('request','response','notify','vote','heartbeat','task_result')),
            content      JSONB,
            reply_to     TEXT REFERENCES agent_messages(message_id) ON DELETE SET NULL,
            metadata     JSONB DEFAULT '{}',
            created_at   TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_messages_channel ON agent_messages(channel_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_messages_sender ON agent_messages(sender_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_messages_type ON agent_messages(message_type)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_messages_reply_to ON agent_messages(reply_to)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_messages_created ON agent_messages(created_at)"
    )
