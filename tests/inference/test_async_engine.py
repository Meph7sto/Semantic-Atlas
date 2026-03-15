"""
异步Engine性能测试

测试asyncio + aiohttp升级后的性能提升。
"""
import asyncio
import time
from typing import List
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend_inference.core.engine import DeepSeekEngine


# ========================================
# 测试配置
# ========================================
TEST_DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "your-api-key-here")
TEST_DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1")
TEST_MODEL = "deepseek-chat"

# 测试参数
CONCURRENT_REQUESTS = 5  # 并发请求数
TEST_PROMPT = "Say 'Hello' in 3 words"
TEST_SYSTEM_PROMPT = "You are a helpful assistant."
MAX_TOKENS = 50


# ========================================
# 基础功能测试
# ========================================


async def test_async_generate():
    """测试基础异步生成功能"""
    print("\n=== 测试1: 异步生成 (generate_async) ===")

    engine = DeepSeekEngine(
        model_path="",
        provider="deepseek",
        deepseek_api_url=TEST_DEEPSEEK_API_URL,
        deepseek_api_key=TEST_DEEPSEEK_API_KEY,
        deepseek_model=TEST_MODEL,
    )

    try:
        start = time.time()
        result = await engine.generate_async(
            prompt=TEST_PROMPT,
            system_prompt=TEST_SYSTEM_PROMPT,
            max_new_tokens=MAX_TOKENS,
        )
        elapsed = time.time() - start

        print(f"✅ 成功!")
        print(f"📝 响应: {result[:100]}...")
        print(f"⏱️  耗时: {elapsed:.2f}秒")
        return True

    except Exception as e:
        print(f"❌ 失败: {e}")
        return False
    finally:
        await engine.close_async()


async def test_async_generate_stream():
    """测试异步流式生成功能"""
    print("\n=== 测试2: 异步流式生成 (generate_stream_async) ===")

    engine = DeepSeekEngine(
        model_path="",
        provider="deepseek",
        deepseek_api_url=TEST_DEEPSEEK_API_URL,
        deepseek_api_key=TEST_DEEPSEEK_API_KEY,
        deepseek_model=TEST_MODEL,
    )

    try:
        start = time.time()
        chunks = []

        async for chunk in engine.generate_stream_async(
            prompt=TEST_PROMPT,
            system_prompt=TEST_SYSTEM_PROMPT,
            max_new_tokens=MAX_TOKENS,
        ):
            chunks.append(chunk)
            # 实时打印前几个chunk
            if len(chunks) <= 3:
                print(f"📦 Chunk {len(chunks)}: {chunk}")

        elapsed = time.time() - start
        full_text = "".join([c.get("delta", "") for c in chunks])

        print(f"✅ 成功!")
        print(f"📝 完整响应: {full_text[:100]}...")
        print(f"📊 总chunk数: {len(chunks)}")
        print(f"⏱️  耗时: {elapsed:.2f}秒")
        return True

    except Exception as e:
        print(f"❌ 失败: {e}")
        return False
    finally:
        await engine.close_async()


async def test_async_generate_with_tools():
    """测试异步工具调用功能"""
    print("\n=== 测试3: 异步工具调用 (generate_with_tools_async) ===")

    engine = DeepSeekEngine(
        model_path="",
        provider="deepseek",
        deepseek_api_url=TEST_DEEPSEEK_API_URL,
        deepseek_api_key=TEST_DEEPSEEK_API_KEY,
        deepseek_model=TEST_MODEL,
    )

    # 定义一个简单的工具
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather in a location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The city name, e.g. San Francisco",
                        },
                        "unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                        },
                    },
                    "required": ["location"],
                },
            },
        }
    ]

    messages = [
        {"role": "user", "content": "What's the weather in Beijing?"}
    ]

    try:
        start = time.time()
        result = await engine.generate_with_tools_async(
            messages=messages,
            tools=tools,
            max_new_tokens=MAX_TOKENS,
        )
        elapsed = time.time() - start

        print(f"✅ 成功!")
        print(f"📝 Content: {result.content}")
        print(f"🔧 Tool calls: {result.tool_calls}")
        print(f"🧠 Reasoning: {result.reasoning_content}")
        print(f"🏁 Finish reason: {result.finish_reason}")
        print(f"⏱️  耗时: {elapsed:.2f}秒")
        return True

    except Exception as e:
        print(f"❌ 失败: {e}")
        return False
    finally:
        await engine.close_async()


# ========================================
# 性能对比测试
# ========================================


def test_sync_performance():
    """同步版本性能测试（作为对照组）"""
    print(f"\n=== 性能测试A: 同步版本 ({CONCURRENT_REQUESTS}个连续请求) ===")

    engine = DeepSeekEngine(
        model_path="",
        provider="deepseek",
        deepseek_api_url=TEST_DEEPSEEK_API_URL,
        deepseek_api_key=TEST_DEEPSEEK_API_KEY,
        deepseek_model=TEST_MODEL,
    )

    start = time.time()

    # 同步顺序执行
    results = []
    for i in range(CONCURRENT_REQUESTS):
        try:
            result = engine.generate(
                prompt=f"Say hello in {i+1} words",
                system_prompt=TEST_SYSTEM_PROMPT,
                max_new_tokens=MAX_TOKENS,
            )
            results.append(result)
            print(f"  完成请求 {i+1}/{CONCURRENT_REQUESTS}")
        except Exception as e:
            print(f"  ❌ 请求 {i+1} 失败: {e}")

    elapsed = time.time() - start

    print(f"\n📊 同步版本结果:")
    print(f"  总耗时: {elapsed:.2f}秒")
    print(f"  平均耗时: {elapsed/CONCURRENT_REQUESTS:.2f}秒/请求")
    print(f"  成功数: {len(results)}/{CONCURRENT_REQUESTS}")

    return elapsed


async def test_async_performance():
    """异步版本性能测试（并发执行）"""
    print(f"\n=== 性能测试B: 异步版本 ({CONCURRENT_REQUESTS}个并发请求) ===")

    engine = DeepSeekEngine(
        model_path="",
        provider="deepseek",
        deepseek_api_url=TEST_DEEPSEEK_API_URL,
        deepseek_api_key=TEST_DEEPSEEK_API_KEY,
        deepseek_model=TEST_MODEL,
    )

    async def single_request(i: int):
        """单个异步请求"""
        try:
            result = await engine.generate_async(
                prompt=f"Say hello in {i+1} words",
                system_prompt=TEST_SYSTEM_PROMPT,
                max_new_tokens=MAX_TOKENS,
            )
            print(f"  完成请求 {i+1}/{CONCURRENT_REQUESTS}")
            return result
        except Exception as e:
            print(f"  ❌ 请求 {i+1} 失败: {e}")
            return None

    start = time.time()

    # 异步并发执行
    tasks = [single_request(i) for i in range(CONCURRENT_REQUESTS)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = time.time() - start

    # 过滤成功的结果
    successful_results = [r for r in results if r is not None and not isinstance(r, Exception)]

    print(f"\n📊 异步版本结果:")
    print(f"  总耗时: {elapsed:.2f}秒")
    print(f"  平均耗时: {elapsed/CONCURRENT_REQUESTS:.2f}秒/请求")
    print(f"  成功数: {len(successful_results)}/{CONCURRENT_REQUESTS}")

    await engine.close_async()
    return elapsed


async def test_performance_comparison():
    """性能对比测试"""
    print("\n" + "=" * 60)
    print("性能对比测试")
    print("=" * 60)

    # 运行同步版本测试
    sync_time = test_sync_performance()

    # 等待一下，避免API限流
    await asyncio.sleep(2)

    # 运行异步版本测试
    async_time = await test_async_performance()

    # 计算性能提升
    speedup = sync_time / async_time if async_time > 0 else 0

    print("\n" + "=" * 60)
    print("📈 性能对比总结")
    print("=" * 60)
    print(f"  同步版本总耗时: {sync_time:.2f}秒")
    print(f"  异步版本总耗时: {async_time:.2f}秒")
    print(f"  性能提升: {speedup:.2f}x 倍")
    print(f"  节省时间: {sync_time - async_time:.2f}秒 ({(sync_time - async_time) / sync_time * 100:.1f}%)")
    print("=" * 60)


# ========================================
# 并发压力测试
# ========================================


async def test_high_concurrency():
    """高并发压力测试"""
    print("\n=== 测试4: 高并发压力测试 (20个并发请求) ===")

    engine = DeepSeekEngine(
        model_path="",
        provider="deepseek",
        deepseek_api_url=TEST_DEEPSEEK_API_URL,
        deepseek_api_key=TEST_DEEPSEEK_API_KEY,
        deepseek_model=TEST_MODEL,
    )

    async def single_request(i: int):
        try:
            result = await engine.generate_async(
                prompt=f"Count to {i}",
                system_prompt=TEST_SYSTEM_PROMPT,
                max_new_tokens=30,
            )
            return True
        except Exception as e:
            print(f"  ❌ 请求 {i} 失败: {e}")
            return False

    start = time.time()
    tasks = [single_request(i) for i in range(1, 21)]
    results = await asyncio.gather(*tasks)
    elapsed = time.time() - start

    success_count = sum(1 for r in results if r)

    print(f"✅ 完成!")
    print(f"📊 成功率: {success_count}/20 ({success_count/20*100:.1f}%)")
    print(f"⏱️  总耗时: {elapsed:.2f}秒")
    print(f"⚡ 平均响应时间: {elapsed/20:.2f}秒/请求")

    await engine.close_async()


# ========================================
# Session复用测试
# ========================================


async def test_session_reuse():
    """测试Session复用（性能优化关键）"""
    print("\n=== 测试5: Session复用测试 ===")

    engine = DeepSeekEngine(
        model_path="",
        provider="deepseek",
        deepseek_api_url=TEST_DEEPSEEK_API_URL,
        deepseek_api_key=TEST_DEEPSEEK_API_KEY,
        deepseek_model=TEST_MODEL,
    )

    # 连续发送多个请求，观察session是否复用
    start = time.time()

    for i in range(3):
        result = await engine.generate_async(
            prompt=f"Say hi {i+1}",
            system_prompt=TEST_SYSTEM_PROMPT,
            max_new_tokens=20,
        )
        print(f"  请求 {i+1}: {result[:30]}...")

    elapsed = time.time() - start

    print(f"✅ 完成!")
    print(f"⏱️  3个请求总耗时: {elapsed:.2f}秒")
    print(f"💡 提示: 如果session正确复用，第2、3个请求应该更快")

    await engine.close_async()


# ========================================
# 主测试运行器
# ========================================


async def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("🚀 异步Engine测试套件")
    print("=" * 60)
    print(f"测试环境:")
    print(f"  API URL: {TEST_DEEPSEEK_API_URL}")
    print(f"  Model: {TEST_MODEL}")
    print(f"  API Key: {'已配置' if TEST_DEEPSEEK_API_KEY and TEST_DEEPSEEK_API_KEY != 'your-api-key-here' else '未配置 ⚠️'}")
    print("=" * 60)

    if TEST_DEEPSEEK_API_KEY == "your-api-key-here":
        print("\n⚠️  警告: 请设置环境变量 DEEPSEEK_API_KEY")
        print("   export DEEPSEEK_API_KEY=your-actual-api-key")
        return

    test_results = []

    # 基础功能测试
    test_results.append(("异步生成", await test_async_generate()))
    await asyncio.sleep(1)

    test_results.append(("异步流式生成", await test_async_generate_stream()))
    await asyncio.sleep(1)

    test_results.append(("异步工具调用", await test_async_generate_with_tools()))
    await asyncio.sleep(1)

    # Session复用测试
    await test_session_reuse()
    await asyncio.sleep(1)

    # 高并发测试
    await test_high_concurrency()
    await asyncio.sleep(2)

    # 性能对比测试
    await test_performance_comparison()

    # 总结
    print("\n" + "=" * 60)
    print("📋 测试总结")
    print("=" * 60)
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name}: {status}")
    print("=" * 60)


async def run_quick_test():
    """快速测试（仅测试基本功能）"""
    print("\n🚀 快速测试模式\n")

    if TEST_DEEPSEEK_API_KEY == "your-api-key-here":
        print("⚠️  请设置 DEEPSEEK_API_KEY 环境变量")
        return

    await test_async_generate()
    await asyncio.sleep(1)
    await test_async_generate_stream()


# ========================================
# 使用示例
# ========================================


async def example_usage():
    """异步Engine使用示例"""
    print("\n" + "=" * 60)
    print("📚 异步Engine使用示例")
    print("=" * 60)

    # 创建engine实例
    engine = DeepSeekEngine(
        model_path="",
        provider="deepseek",
        deepseek_api_url=TEST_DEEPSEEK_API_URL,
        deepseek_api_key=TEST_DEEPSEEK_API_KEY,
        deepseek_model=TEST_MODEL,
    )

    # 示例1: 单个异步请求
    print("\n1️⃣  单个异步请求:")
    result = await engine.generate_async(
        prompt="What is Python?",
        system_prompt="You are a helpful assistant.",
        max_new_tokens=50,
    )
    print(f"   响应: {result[:80]}...")

    # 示例2: 并发多个请求
    print("\n2️⃣  并发3个请求:")
    tasks = [
        engine.generate_async("What is AI?", "You are helpful.", 30),
        engine.generate_async("What is ML?", "You are helpful.", 30),
        engine.generate_async("What is DL?", "You are helpful.", 30),
    ]
    results = await asyncio.gather(*tasks)
    for i, result in enumerate(results, 1):
        print(f"   请求{i}: {result[:50]}...")

    # 示例3: 流式响应
    print("\n3️⃣  流式响应:")
    print("   ", end="")
    async for chunk in engine.generate_stream_async(
        "Count from 1 to 5", "You are helpful.", 30
    ):
        print(chunk.get("delta", ""), end="", flush=True)
    print()

    # 清理资源
    await engine.close_async()
    print("\n✅ 示例完成!\n")


# ========================================
# 主入口
# ========================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="异步Engine测试套件")
    parser.add_argument(
        "--mode",
        choices=["all", "quick", "perf", "example"],
        default="quick",
        help="测试模式: all(完整测试), quick(快速测试), perf(仅性能测试), example(使用示例)",
    )

    args = parser.parse_args()

    if args.mode == "all":
        asyncio.run(run_all_tests())
    elif args.mode == "quick":
        asyncio.run(run_quick_test())
    elif args.mode == "perf":
        asyncio.run(test_performance_comparison())
    elif args.mode == "example":
        asyncio.run(example_usage())
