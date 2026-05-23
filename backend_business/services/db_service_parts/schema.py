from .schemas.agent_chat_schema import init_agent_chat_schema
from .schemas.auth_user_schema import init_auth_user_schema
from .schemas.execution_schema import init_execution_schema
from .schemas.project_schema import init_project_schema
from .schemas.requirement_actor_schema import init_requirement_actor_schema
from .schemas.requirement_schema import init_requirement_schema
from .schemas.trace_schema import init_trace_schema
from .schemas.transcription_schema import init_transcription_schema
from .schemas.usage_schema import init_usage_schema


def init_all_schemas(cur):
    # Keep this order to satisfy cross-table references and ALTER dependencies.
    init_trace_schema(cur)
    init_requirement_schema(cur)
    init_project_schema(cur)
    init_agent_chat_schema(cur)
    init_auth_user_schema(cur)
    init_usage_schema(cur)
    init_execution_schema(cur)
    init_requirement_actor_schema(
        cur
    )  # Must be after project_schema for manage_requirements ALTER
    init_transcription_schema(cur)


def init_db(conn):
    with conn.cursor() as cur:
        init_all_schemas(cur)
