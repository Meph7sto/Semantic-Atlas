-- Drop assistant/agent-task tables removed from application code.
-- Execute this script only AFTER deploying code that no longer references these tables.

DROP TABLE IF EXISTS agent_pending_tasks;
DROP TABLE IF EXISTS ai_chat_messages;
DROP TABLE IF EXISTS ai_chat_sessions;
