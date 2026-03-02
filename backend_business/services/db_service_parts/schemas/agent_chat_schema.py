def init_agent_chat_schema(cur):
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
    # AI Chat Sessions Table (AI 聊天会话)
    # ========================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_chat_sessions (
            session_id TEXT PRIMARY KEY,
            project_id TEXT REFERENCES manage_projects(project_id) ON DELETE SET NULL,
            user_id TEXT NOT NULL,
            title TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_chat_sessions_project ON ai_chat_sessions(project_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_chat_sessions_user ON ai_chat_sessions(user_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_chat_sessions_updated ON ai_chat_sessions(updated_at)"
    )

    # ========================
    # AI Chat Messages Table (AI 聊天消息)
    # ========================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_chat_messages (
            message_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES ai_chat_sessions(session_id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            metadata JSONB,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_chat_messages_session ON ai_chat_messages(session_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_chat_messages_created ON ai_chat_messages(created_at)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_chat_messages_unread ON ai_chat_messages(session_id, is_read) WHERE is_read = FALSE"
    )

    # ========================
    # Agent Pending Tasks Table (Agent 待审任务)
    # ========================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_pending_tasks (
            task_id TEXT PRIMARY KEY,
            session_id TEXT REFERENCES ai_chat_sessions(session_id) ON DELETE CASCADE,
            project_id TEXT REFERENCES manage_projects(project_id) ON DELETE SET NULL,
            user_id TEXT NOT NULL,
            task_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            payload JSONB,
            status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMPTZ
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_tasks_user ON agent_pending_tasks(user_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_tasks_project ON agent_pending_tasks(project_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_tasks_status ON agent_pending_tasks(status)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_tasks_pending ON agent_pending_tasks(user_id, status) WHERE status = 'pending'"
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
