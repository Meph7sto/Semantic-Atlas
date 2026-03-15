def init_transcription_schema(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transcription_sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'timeout')),
            source_filename TEXT NOT NULL,
            source_extension TEXT NOT NULL,
            source_content_type TEXT,
            source_size_bytes BIGINT NOT NULL DEFAULT 0,
            source_storage_path TEXT NOT NULL,
            remote_request_id TEXT,
            transcript_text TEXT,
            transcript_segments JSONB,
            transcript_metadata JSONB,
            error_code TEXT,
            error_message TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transcription_attempts (
            id SERIAL PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES transcription_sessions(session_id) ON DELETE CASCADE,
            attempt_no INTEGER NOT NULL,
            status TEXT NOT NULL
                CHECK (status IN ('running', 'succeeded', 'failed', 'timeout')),
            remote_request_id TEXT,
            error_code TEXT,
            error_message TEXT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            metadata JSONB,
            UNIQUE(session_id, attempt_no)
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_transcription_sessions_user_created ON transcription_sessions(user_id, created_at DESC)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_transcription_sessions_status ON transcription_sessions(status)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_transcription_attempts_session ON transcription_attempts(session_id, attempt_no DESC)"
    )
