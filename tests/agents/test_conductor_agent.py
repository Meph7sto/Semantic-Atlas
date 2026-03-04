"""Conductor agent and messaging tool behavior tests."""

import os
import sys
import unittest
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SKIP_DB_INIT", "1")

from backend_business.services.agent.agents import (  # noqa: E402
    conductor_agent as _conductor_agent_module,
)
from backend_business.services.agent.agents import (  # noqa: E402
    requirements_agent as _requirements_agent_module,
)
from backend_business.services.agent.context import (  # noqa: E402
    AgentContext,
    BaseContext,
    ExecutionContext,
)
from backend_business.services.agent.registry import agent_registry  # noqa: E402
from backend_business.services.agent.tools.base import (  # noqa: E402
    ToolDefinition,
    tool_registry,
)
from backend_business.routes.agent_monitor_routes import (  # noqa: E402
    _filter_messages_by_project,
)
from backend_business.services.agent.messaging.channel import (  # noqa: E402
    ChannelManager,
)
from backend_business.services.agent.tools import (  # noqa: E402
    messaging_tools as messaging_tools_module,
)


def _dummy_schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"dummy schema for {name}",
            "parameters": {"type": "object", "properties": {}},
        },
    }


def _noop_handler(_args, _ctx):
    return {"ok": True}


class TestConductorAgent(unittest.TestCase):
    def test_project_filter_keeps_reply_messages_in_same_channel(self):
        messages = [
            {"message_id": "msg_1", "channel_id": "ch_1", "project_id": "p1"},
            {"message_id": "msg_2", "channel_id": "ch_1", "project_id": None},
            {"message_id": "msg_3", "channel_id": "ch_2", "project_id": "p2"},
        ]
        filtered = _filter_messages_by_project(messages, "p1")
        filtered_ids = [m["message_id"] for m in filtered]
        self.assertListEqual(filtered_ids, ["msg_1", "msg_2"])

    def test_direct_channel_project_id_is_persisted(self):
        manager = ChannelManager()
        channel = manager.get_or_create_direct_channel(
            "conductor_agent", "requirements_agent", project_id="p1"
        )
        self.assertEqual(channel.project_id, "p1")

        # Existing channel can be upgraded with project context when absent.
        channel.project_id = None
        upgraded = manager.get_or_create_direct_channel(
            "conductor_agent", "requirements_agent", project_id="p2"
        )
        self.assertEqual(upgraded.channel_id, channel.channel_id)
        self.assertEqual(upgraded.project_id, "p2")

    def test_conductor_registered_as_orchestrator_only(self):
        agent_def = agent_registry.get("conductor_agent")
        self.assertIsNotNone(agent_def)
        self.assertEqual(agent_def.agent_id, "conductor_agent")
        self.assertIn("delegate_task", agent_def.tool_names)
        self.assertIn("query_agent", agent_def.tool_names)
        self.assertNotIn("requirement_update", agent_def.tool_names)
        self.assertEqual(agent_def.child_agent_ids, ["requirements_agent"])

    def test_messaging_tools_registered_with_openai_schema(self):
        delegate_tool = tool_registry.get("delegate_task")
        query_tool = tool_registry.get("query_agent")
        self.assertIsNotNone(delegate_tool)
        self.assertIsNotNone(query_tool)
        self.assertEqual(
            delegate_tool.openai_schema["function"]["name"], "delegate_task"
        )
        self.assertEqual(query_tool.openai_schema["function"]["name"], "query_agent")

    def test_delegate_task_rejects_unauthorized_target(self):
        ctx = AgentContext(
            base=BaseContext(user_id="u1", session_id="s1", project_id="p1"),
            execution=ExecutionContext(agent_id="requirements_agent"),
        )
        result = messaging_tools_module._delegate_task(
            {
                "target_agent_id": "conductor_agent",
                "task_description": "delegate to parent should fail",
            },
            ctx,
        )
        self.assertIn("error", result)
        self.assertIn("not allowed", result["error"])

    @patch.object(
        messaging_tools_module,
        "_run_target_agent",
        return_value={
            "agent_id": "requirements_agent",
            "content": "delegated done",
            "tasks_created": [],
            "errors": [],
            "rounds_used": 1,
        },
    )
    @patch.object(messaging_tools_module.message_bus, "send_response", return_value="msg_res")
    @patch.object(messaging_tools_module.message_bus, "send_request", return_value="msg_req")
    def test_delegate_task_executes_child_agent(
        self,
        _mock_send_request,
        _mock_send_response,
        mock_run_target,
    ):
        ctx = AgentContext(
            base=BaseContext(user_id="u1", session_id="s1", project_id="p1"),
            execution=ExecutionContext(agent_id="conductor_agent"),
        )

        result = messaging_tools_module._delegate_task(
            {
                "target_agent_id": "requirements_agent",
                "task_description": "search requirements and summarize",
                "task_context": {"priority": "high"},
            },
            ctx,
        )

        self.assertEqual(result["status"], "delegated")
        self.assertEqual(result["request_message_id"], "msg_req")
        self.assertEqual(result["response_message_id"], "msg_res")
        self.assertIn("result", result)
        self.assertTrue(mock_run_target.called)

    @patch.object(
        messaging_tools_module,
        "_run_target_agent",
        return_value={
            "agent_id": "requirements_agent",
            "content": "query done",
            "tasks_created": [],
            "errors": [],
            "rounds_used": 1,
        },
    )
    @patch.object(messaging_tools_module.message_bus, "send_response", return_value="msg_res")
    @patch.object(messaging_tools_module.message_bus, "send_request", return_value="msg_req")
    def test_query_agent_uses_read_only_tools(
        self,
        _mock_send_request,
        _mock_send_response,
        mock_run_target,
    ):
        # Register minimal tool metadata so read-only filter can be tested in isolation.
        tool_registry.register(
            ToolDefinition(
                name="requirement_search",
                openai_schema=_dummy_schema("requirement_search"),
                handler=_noop_handler,
                is_write=False,
            )
        )
        tool_registry.register(
            ToolDefinition(
                name="requirement_get",
                openai_schema=_dummy_schema("requirement_get"),
                handler=_noop_handler,
                is_write=False,
            )
        )
        tool_registry.register(
            ToolDefinition(
                name="requirement_update",
                openai_schema=_dummy_schema("requirement_update"),
                handler=_noop_handler,
                is_write=True,
            )
        )

        ctx = AgentContext(
            base=BaseContext(user_id="u1", session_id="s1", project_id="p1"),
            execution=ExecutionContext(agent_id="conductor_agent"),
        )
        result = messaging_tools_module._query_agent(
            {
                "target_agent_id": "requirements_agent",
                "query": "list top priority requirements",
            },
            ctx,
        )

        self.assertEqual(result["status"], "query_completed")
        _, kwargs = mock_run_target.call_args
        self.assertEqual(kwargs["target_agent_id"], "requirements_agent")
        self.assertListEqual(
            kwargs["tool_names_override"], ["requirement_search", "requirement_get"]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
