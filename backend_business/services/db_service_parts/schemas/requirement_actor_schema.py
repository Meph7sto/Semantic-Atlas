"""
RequirementActor 相关数据库表定义

遵循现有 Schema 模式：init_*_schema(cur)
"""

def init_requirement_actor_schema(cur):
    """初始化 RequirementActor 相关表"""

    # ========================
    # 事件存储表（仅追加）
    # ========================
    cur.execute("""
        CREATE TABLE IF NOT EXISTS requirement_events (
            event_id TEXT PRIMARY KEY,
            requirement_id TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK (event_type IN (
                'RequirementContentUpdated',
                'RequirementStatusChanged',
                'RequirementQualityMarkerAdded',
                'RequirementEvidenceLinkAdded',
                'RequirementPriorityChanged',
                'RequirementCreated',
                'RequirementDeleted'
            )),
            event_sequence INTEGER NOT NULL,
            event_data JSONB NOT NULL,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            source TEXT NOT NULL,
            metadata JSONB DEFAULT '{}',
            CONSTRAINT uk_requirement_events UNIQUE (requirement_id, event_sequence)
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_req_events_req_id ON requirement_events(requirement_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_req_events_seq ON requirement_events(requirement_id, event_sequence)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_req_events_type ON requirement_events(event_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_req_events_occurred_at ON requirement_events(occurred_at DESC)")

    # Monotonic fencing tokens prevent an expired Actor lease from writing
    # after a newer owner has taken over the same requirement.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS requirement_actor_fences (
            requirement_id TEXT PRIMARY KEY,
            fencing_token BIGINT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ========================
    # 快照存储表
    # ========================
    cur.execute("""
        CREATE TABLE IF NOT EXISTS requirement_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            requirement_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            snapshot_data JSONB NOT NULL,
            snapshot_reason TEXT CHECK (snapshot_reason IN ('scheduled', 'manual', 'passivation')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            event_count INTEGER DEFAULT 0
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_req_snapshots_req_id ON requirement_snapshots(requirement_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_req_snapshots_version ON requirement_snapshots(requirement_id, version DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_req_snapshots_created_at ON requirement_snapshots(created_at DESC)")

    # ========================
    # 命令队列审计日志表
    # ========================
    cur.execute("""
        CREATE TABLE IF NOT EXISTS requirement_command_queue (
            queue_id TEXT PRIMARY KEY,
            requirement_id TEXT NOT NULL,
            command_type TEXT NOT NULL,
            command_data JSONB NOT NULL,
            submitted_by TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            error_message TEXT,
            priority INTEGER DEFAULT 0
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_cmd_queue_req_id ON requirement_command_queue(requirement_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cmd_queue_status ON requirement_command_queue(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cmd_queue_submitted_at ON requirement_command_queue(submitted_at DESC)")

    # ========================
    # 扩展现有 manage_requirements 表
    # ========================
    cur.execute("ALTER TABLE manage_requirements ADD COLUMN IF NOT EXISTS current_version INTEGER DEFAULT 0")
    cur.execute("ALTER TABLE manage_requirements ADD COLUMN IF NOT EXISTS last_event_id TEXT")
    cur.execute("ALTER TABLE manage_requirements ADD COLUMN IF NOT EXISTS last_snapshot_id TEXT")
    cur.execute("ALTER TABLE manage_requirements ADD COLUMN IF NOT EXISTS actor_status TEXT DEFAULT 'inactive'")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_manage_requirements_actor_status ON manage_requirements(actor_status)")
