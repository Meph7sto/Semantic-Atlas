"""
DeepSeek Tool Calls 功能测试脚本

使用方法:
    python tests/test_tool_calls.py

需要设置环境变量:
    DEEPSEEK_API_KEY=your_api_key
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend_inference.core.engine import DeepSeekEngine, ToolCallResult


def test_tool_calls_non_stream():
    """测试非流式 Tool Calls"""
    print("=" * 50)
    print("测试非流式 Tool Calls")
    print("=" * 50)
    
    engine = DeepSeekEngine(
        model_path="",
        provider="deepseek",
    )
    engine.load_model()
    
    # 定义工具
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "获取某个城市的天气信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "城市名称，例如：杭州、北京"
                        }
                    },
                    "required": ["location"]
                }
            }
        }
    ]
    
    # 发送消息
    messages = [
        {"role": "system", "content": "你是一个助手，可以调用工具来获取信息。"},
        {"role": "user", "content": "杭州今天天气怎么样？"}
    ]
    
    print(f"\n用户: {messages[1]['content']}")
    
    result = engine.generate_with_tools(
        messages=messages,
        tools=tools,
        max_new_tokens=1024,
    )
    
    print(f"\n结果类型: {type(result)}")
    print(f"Content: {result.content}")
    print(f"Tool Calls: {result.tool_calls}")
    print(f"Finish Reason: {result.finish_reason}")
    
    # 如果有 tool_calls，模拟执行并继续对话
    if result.tool_calls:
        print("\n--- 模拟执行工具调用 ---")
        for tc in result.tool_calls:
            print(f"调用函数: {tc['function']['name']}")
            print(f"参数: {tc['function']['arguments']}")
            
            # 模拟返回结果
            messages.append({
                "role": "assistant",
                "content": result.content,
                "tool_calls": result.tool_calls
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": "晴天，温度 24℃，湿度 65%"
            })
        
        # 继续对话获取最终回复
        final_result = engine.generate_with_tools(
            messages=messages,
            tools=tools,
            max_new_tokens=1024,
        )
        print(f"\n最终回复: {final_result.content}")
    
    return result


def test_tool_calls_stream():
    """测试流式 Tool Calls"""
    print("\n" + "=" * 50)
    print("测试流式 Tool Calls")
    print("=" * 50)
    
    engine = DeepSeekEngine(
        model_path="",
        provider="deepseek",
    )
    engine.load_model()
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "执行数学计算",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "数学表达式，例如: 2 + 3 * 4"
                        }
                    },
                    "required": ["expression"]
                }
            }
        }
    ]
    
    messages = [
        {"role": "system", "content": "你是一个助手，可以调用计算器工具。"},
        {"role": "user", "content": "请帮我计算 123 * 456 等于多少"}
    ]
    
    print(f"\n用户: {messages[1]['content']}")
    print("\n流式输出:")
    
    content_buffer = ""
    tool_calls_buffer = {}
    
    for chunk in engine.generate_with_tools_stream(
        messages=messages,
        tools=tools,
        max_new_tokens=1024,
    ):
        chunk_type = chunk.get("type")
        
        if chunk_type == "thinking":
            print(f"[思考] {chunk['delta']}", end="", flush=True)
        elif chunk_type == "content":
            content_buffer += chunk["delta"]
            print(chunk["delta"], end="", flush=True)
        elif chunk_type == "tool_call":
            idx = chunk["index"]
            if idx not in tool_calls_buffer:
                tool_calls_buffer[idx] = {
                    "id": chunk["id"],
                    "function": {"name": chunk["function"]["name"], "arguments": ""}
                }
            tool_calls_buffer[idx]["function"]["arguments"] += chunk["function"]["arguments"]
            print(f"\n[Tool Call {idx}] {chunk['function']['name']}: {chunk['function']['arguments']}", end="", flush=True)
        elif chunk_type == "finish":
            print(f"\n[完成] finish_reason: {chunk['finish_reason']}")
    
    print(f"\n\n最终 content: {content_buffer}")
    print(f"Tool calls: {tool_calls_buffer}")


if __name__ == "__main__":
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("错误: 请设置 DEEPSEEK_API_KEY 环境变量")
        print("例如: set DEEPSEEK_API_KEY=your_key")
        sys.exit(1)
    
    try:
        test_tool_calls_non_stream()
        test_tool_calls_stream()
        print("\n" + "=" * 50)
        print("所有测试完成!")
        print("=" * 50)
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
