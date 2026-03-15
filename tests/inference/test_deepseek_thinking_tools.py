"""
测试 DeepSeek 深度思考模式 + 工具调用 (Tool Calling)
参考: https://api-docs.deepseek.com/zh-cn/guides/thinking_mode

使用方法:
  1. 设置环境变量 DEEPSEEK_API_KEY 或在下方直接填写
  2. 确保 business backend 运行在 http://localhost:5001
  3. conda activate semantic-Altas
  4. python test_deepseek_thinking_tools.py
"""

import os
import json
import requests
from openai import OpenAI

# ============================================================
# 配置
# ============================================================
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-a9d09986bb8c4527a255b790a47bf5f6")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
BACKEND_BASE_URL = "http://localhost:5001"

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

# ============================================================
# 工具定义 —— 映射到项目真实接口
# ============================================================
tools = [
    {
        "type": "function",
        "function": {
            "name": "health_check",
            "description": "检查业务后端的健康状态，返回后端和推理服务的连通性信息",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_projects",
            "description": "列出所有需求管理项目。返回项目列表，每个项目包含 id、name、description、current_session_id 等字段",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_detail",
            "description": "根据项目ID获取单个项目的详细信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "项目的UUID",
                    }
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_project_requirements",
            "description": "列出指定项目下的所有需求，支持树形结构展示",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "项目的UUID",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["flat", "tree"],
                        "description": "返回格式：flat=扁平列表，tree=树形结构。默认flat",
                    },
                },
                "required": ["project_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_products",
            "description": "列出所有产品线，产品是项目的上层管理单元",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_project",
            "description": "创建一个新的需求管理项目",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "项目名称",
                    },
                    "description": {
                        "type": "string",
                        "description": "项目描述（可选）",
                    },
                },
                "required": ["name"],
            },
        },
    },
]


# ============================================================
# 工具执行器 —— 调用项目真实接口
# ============================================================
def execute_tool(name: str, arguments: dict) -> str:
    """根据工具名称调用对应的后端 API，返回 JSON 字符串结果"""
    try:
        if name == "health_check":
            resp = requests.get(f"{BACKEND_BASE_URL}/api/health", timeout=10)
            return json.dumps(resp.json(), ensure_ascii=False)

        elif name == "list_projects":
            resp = requests.get(f"{BACKEND_BASE_URL}/api/manage/projects", timeout=10)
            return json.dumps(resp.json(), ensure_ascii=False)

        elif name == "get_project_detail":
            pid = arguments["project_id"]
            resp = requests.get(f"{BACKEND_BASE_URL}/api/manage/projects/{pid}", timeout=10)
            return json.dumps(resp.json(), ensure_ascii=False)

        elif name == "list_project_requirements":
            pid = arguments["project_id"]
            fmt = arguments.get("format", "flat")
            resp = requests.get(
                f"{BACKEND_BASE_URL}/api/manage/projects/{pid}/requirements",
                params={"format": fmt},
                timeout=10,
            )
            return json.dumps(resp.json(), ensure_ascii=False)

        elif name == "list_products":
            resp = requests.get(f"{BACKEND_BASE_URL}/api/product/products", timeout=10)
            return json.dumps(resp.json(), ensure_ascii=False)

        elif name == "create_project":
            payload = {"name": arguments["name"]}
            if "description" in arguments:
                payload["description"] = arguments["description"]
            resp = requests.post(
                f"{BACKEND_BASE_URL}/api/manage/projects",
                json=payload,
                timeout=10,
            )
            return json.dumps(resp.json(), ensure_ascii=False)

        else:
            return json.dumps({"error": f"未知工具: {name}"})

    except requests.exceptions.ConnectionError:
        return json.dumps({"error": f"无法连接到后端 {BACKEND_BASE_URL}，请确认服务已启动"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ============================================================
# 清除 reasoning_content（新一轮对话前必须清除）
# ============================================================
def clear_reasoning_content(messages: list):
    """在开始新一轮用户提问前，清除历史消息中的 reasoning_content"""
    for msg in messages:
        if hasattr(msg, "reasoning_content"):
            msg.reasoning_content = None
        elif isinstance(msg, dict) and "reasoning_content" in msg:
            msg["reasoning_content"] = None


# ============================================================
# 单轮对话（含多次工具调用循环）
# ============================================================
def run_single_turn(messages: list, user_query: str, turn_label: str = ""):
    """执行一次用户提问，自动循环处理工具调用，直到模型给出最终回答"""
    print(f"\n{'='*70}")
    print(f"🧑 用户提问{f' ({turn_label})' if turn_label else ''}: {user_query}")
    print(f"{'='*70}")

    messages.append({"role": "user", "content": user_query})

    round_count = 0
    max_rounds = 10  # 防止无限循环

    while round_count < max_rounds:
        round_count += 1
        print(f"\n--- API 调用 (第 {round_count} 轮) ---")

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=tools,
            extra_body={"thinking": {"type": "enabled"}},
            max_tokens=8192,
        )

        choice = response.choices[0]
        assistant_msg = choice.message

        # 打印思考过程
        if hasattr(assistant_msg, "reasoning_content") and assistant_msg.reasoning_content:
            thinking_preview = assistant_msg.reasoning_content[:500]
            if len(assistant_msg.reasoning_content) > 500:
                thinking_preview += f"... (共{len(assistant_msg.reasoning_content)}字符)"
            print(f"\n💭 思考过程:\n{thinking_preview}")

        # 打印文本内容
        if assistant_msg.content:
            print(f"\n💬 模型回复:\n{assistant_msg.content}")

        # 将助手消息加入历史（保留 reasoning_content 以便同轮后续调用）
        messages.append(assistant_msg)

        # 检查是否有工具调用
        if not assistant_msg.tool_calls:
            print(f"\n✅ 模型完成回答 (finish_reason={choice.finish_reason})")
            break

        # 执行工具调用
        print(f"\n🔧 工具调用 ({len(assistant_msg.tool_calls)} 个):")
        for tc in assistant_msg.tool_calls:
            func_name = tc.function.name
            func_args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            print(f"   ├─ {func_name}({json.dumps(func_args, ensure_ascii=False)})")

            result = execute_tool(func_name, func_args)
            result_preview = result[:300]
            if len(result) > 300:
                result_preview += f"... (共{len(result)}字符)"
            print(f"   └─ 返回: {result_preview}")

            # 将工具结果加入消息历史
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    if round_count >= max_rounds:
        print(f"\n⚠️ 达到最大轮次限制 ({max_rounds})，强制结束")

    return messages


# ============================================================
# 主测试流程
# ============================================================
def main():
    print("=" * 70)
    print("  DeepSeek 深度思考 + 工具调用 测试脚本")
    print("  模型: deepseek-chat + thinking.enabled")
    print(f"  后端: {BACKEND_BASE_URL}")
    print("=" * 70)

    messages = [
        {
            "role": "system",
            "content": (
                "你是一个需求工程助手，可以通过工具调用来查询和管理需求工程项目。"
                "当用户询问项目或需求相关信息时，请主动使用工具获取数据后再回答。"
                "回答请使用中文。"
            ),
        }
    ]

    # ────────────────────────────────────────────
    # Turn 1: 需要多步工具调用的复杂任务
    # ────────────────────────────────────────────
    messages = run_single_turn(
        messages,
        "请帮我检查一下后端服务是否正常运行，然后列出所有项目，并告诉我每个项目有多少条需求。",
        turn_label="Turn 1 - 多步工具调用",
    )

    # ────────────────────────────────────────────
    # Turn 2: 新一轮提问（清除旧 reasoning_content）
    # ────────────────────────────────────────────
    clear_reasoning_content(messages)

    messages = run_single_turn(
        messages,
        "列出所有的产品线信息，如果没有产品线就告诉我。",
        turn_label="Turn 2 - 新轮对话",
    )

    # ────────────────────────────────────────────
    # Turn 3: 不需要工具的简单问题（验证模型不会误调工具）
    # ────────────────────────────────────────────
    clear_reasoning_content(messages)

    messages = run_single_turn(
        messages,
        "需求工程中，什么是需求追踪矩阵？请简要说明。",
        turn_label="Turn 3 - 无需工具的知识问答",
    )

    # ────────────────────────────────────────────
    # 测试总结
    # ────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  测试完成！")
    print("=" * 70)

    # 统计
    tool_call_count = 0
    thinking_count = 0
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            tool_call_count += len(msg.tool_calls)
        if hasattr(msg, "reasoning_content") and msg.reasoning_content:
            thinking_count += 1
        elif isinstance(msg, dict) and msg.get("reasoning_content"):
            thinking_count += 1

    print(f"\n📊 统计:")
    print(f"   消息总数: {len(messages)}")
    print(f"   工具调用次数: {tool_call_count}")
    print(f"   含思考过程的回复数: {thinking_count}")
    print(f"   结论: {'✅ 思考模式+工具调用正常工作' if tool_call_count > 0 and thinking_count > 0 else '❌ 测试未通过'}")


if __name__ == "__main__":
    main()
