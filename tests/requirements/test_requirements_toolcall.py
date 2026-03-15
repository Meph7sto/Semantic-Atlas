"""
测试需求抽取 Tool Call 功能

此测试文件验证 DeepSeek API tool call 格式的需求抽取功能。
参考: https://api-docs.deepseek.com/zh-cn/guides/tool_calls

测试内容：
1. RequirementToolDef 工具定义格式
2. RequirementsExecutor 解析 tool_calls 格式
3. AI Proxy tool call 接口调用
4. 完整的需求抽取流程
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRequirementToolDef(unittest.TestCase):
    """测试 RequirementToolDef 工具定义"""

    def test_get_tool_schema_format(self):
        """测试工具 schema 格式符合 DeepSeek API 规范"""
        from backend_business.services.requirements_executor import RequirementToolDef

        schema = RequirementToolDef.get_tool_schema()

        # 验证基本结构
        self.assertEqual(schema["type"], "function")
        self.assertIn("function", schema)

        func = schema["function"]
        self.assertEqual(func["name"], "create_req")
        self.assertIn("description", func)
        self.assertIn("parameters", func)

        # 验证参数结构
        params = func["parameters"]
        self.assertEqual(params["type"], "object")
        self.assertIn("properties", params)
        self.assertIn("required", params)
        self.assertFalse(params.get("additionalProperties", True))  # strict 模式需要

        # 验证 level 参数
        level_prop = params["properties"]["level"]
        self.assertEqual(level_prop["type"], "string")
        self.assertEqual(level_prop["enum"], ["L1", "L2", "L3"])

        # 验证 text 参数
        text_prop = params["properties"]["text"]
        self.assertEqual(text_prop["type"], "string")

        # 验证 required 字段
        self.assertIn("level", params["required"])
        self.assertIn("text", params["required"])

    def test_get_tools_list(self):
        """测试获取工具列表"""
        from backend_business.services.requirements_executor import RequirementToolDef

        tools = RequirementToolDef.get_tools_list()

        self.assertIsInstance(tools, list)
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["function"]["name"], "create_req")

    def test_get_system_prompt(self):
        """测试系统提示词"""
        from backend_business.services.requirements_executor import RequirementToolDef

        prompt = RequirementToolDef.get_system_prompt()

        self.assertIn("需求分析", prompt)
        self.assertIn("L1", prompt)
        self.assertIn("L2", prompt)
        self.assertIn("L3", prompt)


class TestRequirementsExecutorParsing(unittest.TestCase):
    """测试 RequirementsExecutor 解析 tool_calls 格式"""

    def setUp(self):
        """设置测试环境"""
        # 使用模拟 DSN，因为测试不需要真实数据库连接
        self.executor = self._create_executor_with_mock_dsn()

    def _create_executor_with_mock_dsn(self):
        """创建带模拟 DSN 的执行器"""
        from backend_business.services.requirements_executor import RequirementsExecutor

        # 使用一个不会实际连接的 DSN
        return RequirementsExecutor(dsn="postgresql://test:test@localhost:5432/test")

    def test_parse_deepseek_api_toolcalls_format(self):
        """测试解析 DeepSeek API 返回的 tool_calls 格式"""
        # DeepSeek API 返回的格式
        tool_calls = [
            {
                "id": "call_0_create_req_12345",
                "type": "function",
                "function": {
                    "name": "create_req",
                    "arguments": '{"level": "L1", "text": "提升借用审批效率并降低人工核验成本"}',
                },
            },
            {
                "id": "call_1_create_req_67890",
                "type": "function",
                "function": {
                    "name": "create_req",
                    "arguments": '{"level": "L2", "text": "系统应支持在线提交借用申请"}',
                },
            },
            {
                "id": "call_2_create_req_abcde",
                "type": "function",
                "function": {
                    "name": "create_req",
                    "arguments": '{"level": "L3", "text": "系统必须在2秒内完成审批流程验证"}',
                },
            },
        ]

        # 新版本返回 (create_calls, update_calls) 元组
        create_calls, update_calls = self.executor.parse_toolcalls(tool_calls)

        self.assertEqual(len(create_calls), 3)
        self.assertEqual(create_calls[0]["level"], "L1")
        self.assertEqual(create_calls[0]["text"], "提升借用审批效率并降低人工核验成本")
        self.assertEqual(create_calls[1]["level"], "L2")
        self.assertEqual(create_calls[2]["level"], "L3")
        self.assertEqual(len(update_calls), 0)

    def test_parse_toolcalls_with_dict_arguments(self):
        """测试解析 arguments 为字典格式的情况"""
        tool_calls = [
            {
                "id": "call_0",
                "type": "function",
                "function": {
                    "name": "create_req",
                    "arguments": {"level": "L1", "text": "测试需求文本"},
                },
            }
        ]

        create_calls, update_calls = self.executor.parse_toolcalls(tool_calls)

        self.assertEqual(len(create_calls), 1)
        self.assertEqual(create_calls[0]["level"], "L1")
        self.assertEqual(create_calls[0]["text"], "测试需求文本")

    def test_parse_toolcalls_ignores_other_functions(self):
        """测试忽略非 create_req 的工具调用"""
        tool_calls = [
            {
                "id": "call_0",
                "type": "function",
                "function": {
                    "name": "other_function",
                    "arguments": '{"param": "value"}',
                },
            },
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "create_req",
                    "arguments": '{"level": "L1", "text": "有效需求"}',
                },
            },
        ]

        create_calls, update_calls = self.executor.parse_toolcalls(tool_calls)

        self.assertEqual(len(create_calls), 1)
        self.assertEqual(create_calls[0]["text"], "有效需求")

    def test_parse_toolcalls_handles_invalid_json(self):
        """测试处理无效 JSON 的情况"""
        tool_calls = [
            {
                "id": "call_0",
                "type": "function",
                "function": {"name": "create_req", "arguments": "invalid json"},
            },
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "create_req",
                    "arguments": '{"level": "L2", "text": "有效需求"}',
                },
            },
        ]

        create_calls, update_calls = self.executor.parse_toolcalls(tool_calls)

        # 第一个无效 JSON 应该被跳过
        self.assertEqual(len(create_calls), 1)
        self.assertEqual(len(update_calls), 0)
        self.assertEqual(create_calls[0]["level"], "L2")

    def test_parse_toolcalls_handles_none(self):
        """测试处理 None 输入"""
        create_calls, update_calls = self.executor.parse_toolcalls(None)
        self.assertEqual(create_calls, [])
        self.assertEqual(update_calls, [])

    def test_parse_toolcalls_handles_empty_list(self):
        """测试处理空列表"""
        create_calls, update_calls = self.executor.parse_toolcalls([])
        self.assertEqual(create_calls, [])
        self.assertEqual(update_calls, [])

    def test_parse_legacy_call_format(self):
        """测试解析旧的 CALL 行格式（向后兼容）"""
        model_output = '''CALL create_req level="L1" text="提升借用审批效率"
CALL create_req level="L2" text="系统应支持在线提交"'''

        create_calls, update_calls = self.executor.parse_toolcalls(model_output)

        self.assertEqual(len(create_calls), 2)
        self.assertEqual(len(update_calls), 0)
        self.assertEqual(create_calls[0]["level"], "L1")
        self.assertEqual(create_calls[1]["level"], "L2")

    def test_parse_direct_dict_list_format(self):
        """测试解析直接的参数字典列表"""
        direct_list = [
            {"level": "L1", "text": "业务目标"},
            {"level": "L2", "text": "功能需求"},
        ]

        create_calls, update_calls = self.executor.parse_toolcalls(direct_list)

        self.assertEqual(len(create_calls), 2)
        self.assertEqual(len(update_calls), 0)
        self.assertEqual(create_calls[0]["level"], "L1")
        self.assertEqual(create_calls[1]["level"], "L2")


class TestRequirementsExecutorValidation(unittest.TestCase):
    """测试 RequirementsExecutor 参数校验"""

    def setUp(self):
        """设置测试环境"""
        from backend_business.services.requirements_executor import RequirementsExecutor

        self.executor = RequirementsExecutor(
            dsn="postgresql://test:test@localhost:5432/test"
        )

    def test_validate_valid_l1(self):
        """测试验证有效的 L1 需求"""
        call = {"level": "L1", "text": "提升借用审批效率并降低人工核验成本"}

        is_valid, error = self.executor.validate_toolcall(call)

        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_valid_l2(self):
        """测试验证有效的 L2 需求"""
        call = {"level": "L2", "text": "系统应支持在线提交借用申请"}

        is_valid, error = self.executor.validate_toolcall(call)

        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_valid_l3_with_must(self):
        """测试验证包含'系统必须'的 L3 需求"""
        call = {"level": "L3", "text": "系统必须在2秒内完成审批流程验证"}

        is_valid, error = self.executor.validate_toolcall(call)

        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_valid_l3_with_should(self):
        """测试验证包含'应当'的 L3 需求"""
        call = {"level": "L3", "text": "系统应当支持并发用户访问"}

        is_valid, error = self.executor.validate_toolcall(call)

        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_valid_l3_with_shall(self):
        """测试验证包含'shall'的 L3 需求"""
        call = {"level": "L3", "text": "The system shall respond within 2 seconds"}

        is_valid, error = self.executor.validate_toolcall(call)

        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_invalid_level(self):
        """测试验证无效的 level"""
        call = {"level": "L4", "text": "这是一个无效层级的需求"}

        is_valid, error = self.executor.validate_toolcall(call)

        self.assertFalse(is_valid)
        self.assertIn("Invalid level", error)

    def test_validate_text_too_short(self):
        """测试验证文本过短"""
        call = {"level": "L1", "text": "短"}

        is_valid, error = self.executor.validate_toolcall(call)

        self.assertFalse(is_valid)
        self.assertIn("too short", error)

    def test_validate_l3_missing_keywords(self):
        """测试 L3 需求缺少关键词仍可通过"""
        call = {"level": "L3", "text": "这是一个没有必要关键词的L3需求文本"}

        is_valid, error = self.executor.validate_toolcall(call)

        self.assertTrue(is_valid)
        self.assertIsNone(error)


class TestExecuteBundle(unittest.TestCase):
    """测试 execute_bundle 方法"""

    def setUp(self):
        """设置测试环境"""
        from backend_business.services.requirements_executor import RequirementsExecutor

        self.executor = RequirementsExecutor(
            dsn="postgresql://test:test@localhost:5432/test"
        )

    def test_execute_bundle_with_toolcall_format_empty(self):
        """测试使用 tool_call 格式处理空输出"""
        result = self.executor.execute_bundle(
            session_id="test-session",
            anchor_span_id="test-anchor",
            r=2,
            model_output=None,
            use_toolcall_format=True,
        )

        self.assertEqual(result["status"], "empty")

    def test_execute_bundle_with_toolcall_format_empty_list(self):
        """测试使用 tool_call 格式处理空列表"""
        result = self.executor.execute_bundle(
            session_id="test-session",
            anchor_span_id="test-anchor",
            r=2,
            model_output=[],
            use_toolcall_format=True,
        )

        self.assertEqual(result["status"], "empty")

    @patch.object(
        sys.modules.get(
            "backend_business.services.requirements_executor", MagicMock()
        ).RequirementsExecutor
        if sys.modules.get("backend_business.services.requirements_executor")
        else MagicMock(),
        "_connect",
    )
    def test_execute_bundle_with_valid_toolcalls(self):
        """测试使用有效的 tool_calls 执行"""
        # 模拟数据库连接
        from backend_business.services.requirements_executor import RequirementsExecutor

        executor = RequirementsExecutor(
            dsn="postgresql://test:test@localhost:5432/test"
        )

        # 模拟 _connect 方法
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=None)
        mock_cursor.rowcount = 1
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=None)

        with patch.object(executor, "_connect", return_value=mock_conn):
            tool_calls = [
                {
                    "id": "call_0",
                    "type": "function",
                    "function": {
                        "name": "create_req",
                        "arguments": '{"level": "L1", "text": "提升借用审批效率并降低人工核验成本"}',
                    },
                }
            ]

            result = executor.execute_bundle(
                session_id="test-session",
                anchor_span_id="test-anchor",
                r=2,
                model_output=tool_calls,
                use_toolcall_format=True,
            )

            self.assertEqual(result["parsed_count"], 1)
            self.assertIn(result["status"], ["success", "partial_success"])


class TestToolCallIntegration(unittest.TestCase):
    """集成测试：测试完整的 tool call 流程"""

    def test_tool_schema_is_json_serializable(self):
        """测试工具 schema 可以序列化为 JSON"""
        from backend_business.services.requirements_executor import RequirementToolDef

        tools = RequirementToolDef.get_tools_list()

        # 应该能序列化为 JSON
        json_str = json.dumps(tools, ensure_ascii=False)
        self.assertIsInstance(json_str, str)

        # 应该能反序列化回来
        parsed = json.loads(json_str)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["function"]["name"], "create_req")

    def test_simulated_api_response_parsing(self):
        """测试模拟的 API 响应解析"""
        from backend_business.services.requirements_executor import RequirementsExecutor

        # 模拟 DeepSeek API 的完整响应结构
        api_response = {
            "content": None,
            "tool_calls": [
                {
                    "id": "call_0_create_req_abc123",
                    "type": "function",
                    "function": {
                        "name": "create_req",
                        "arguments": json.dumps(
                            {
                                "level": "L1",
                                "text": "提升借用审批效率并降低人工核验成本",
                            }
                        ),
                    },
                },
                {
                    "id": "call_1_create_req_def456",
                    "type": "function",
                    "function": {
                        "name": "create_req",
                        "arguments": json.dumps(
                            {"level": "L2", "text": "系统应支持在线提交借用申请"}
                        ),
                    },
                },
                {
                    "id": "call_2_create_req_ghi789",
                    "type": "function",
                    "function": {
                        "name": "create_req",
                        "arguments": json.dumps(
                            {"level": "L3", "text": "系统必须在2秒内完成审批流程验证"}
                        ),
                    },
                },
            ],
            "reasoning_content": None,
            "finish_reason": "tool_calls",
        }

        executor = RequirementsExecutor(
            dsn="postgresql://test:test@localhost:5432/test"
        )

        # 解析 tool_calls
        tool_calls = api_response["tool_calls"]
        create_calls, update_calls = executor.parse_toolcalls(tool_calls)

        self.assertEqual(len(create_calls), 3)
        self.assertEqual(len(update_calls), 0)

        # 验证每个解析结果
        for i, call in enumerate(create_calls):
            is_valid, error = executor.validate_toolcall(call)
            self.assertTrue(is_valid, f"Call {i} validation failed: {error}")


class TestChatRouterToolsEndpoint(unittest.TestCase):
    """测试 chat router 的 tools endpoint"""

    def test_chat_completion_with_tools_request_model(self):
        """测试请求模型结构"""
        from backend_inference.routers.chat import (
            ChatCompletionWithToolsRequest,
            ChatMessage,
        )

        # 构建请求
        request = ChatCompletionWithToolsRequest(
            messages=[
                ChatMessage(role="system", content="你是一个需求分析助手"),
                ChatMessage(role="user", content="请分析以下需求..."),
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "create_req",
                        "description": "创建需求",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "level": {"type": "string", "enum": ["L1", "L2", "L3"]},
                                "text": {"type": "string"},
                            },
                            "required": ["level", "text"],
                        },
                    },
                }
            ],
            model="deepseek-chat",
            temperature=0.3,
            tool_choice="auto",
        )

        self.assertEqual(len(request.messages), 2)
        self.assertEqual(len(request.tools), 1)
        self.assertEqual(request.tool_choice, "auto")

    def test_chat_completion_with_tools_response_model(self):
        """测试响应模型结构"""
        from backend_inference.routers.chat import ChatCompletionWithToolsResponse

        # 构建响应
        response = ChatCompletionWithToolsResponse(
            content=None,
            tool_calls=[
                {
                    "id": "call_0",
                    "type": "function",
                    "function": {
                        "name": "create_req",
                        "arguments": '{"level": "L1", "text": "测试需求"}',
                    },
                }
            ],
            reasoning_content=None,
            finish_reason="tool_calls",
        )

        self.assertIsNone(response.content)
        self.assertEqual(len(response.tool_calls), 1)
        self.assertEqual(response.finish_reason, "tool_calls")


if __name__ == "__main__":
    unittest.main(verbosity=2)
