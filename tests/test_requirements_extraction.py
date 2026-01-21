"""
需求抽取功能测试脚本
演示如何使用新实现的 L1-L3 需求抽取功能
"""
import json
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend_business.services.ego_bundle_generator import EgoBundleGenerator
from backend_business.services.requirements_executor import (
    RequirementsExecutor,
    RequirementToolDef,
)


def test_ego_bundle_generator():
    """测试 EgoBundle 生成器"""
    print("=== 测试 EgoBundle 生成器 ===\n")

    # 模拟 spans 数据
    spans = [
        {
            "span_id": "span_001",
            "session_id": "test_session",
            "start_ms": 0,
            "end_ms": 5000,
            "speaker": "产品经理",
            "text": "我们需要提升借用审批效率，降低人工核验成本",
        },
        {
            "span_id": "span_002",
            "session_id": "test_session",
            "start_ms": 5000,
            "end_ms": 10000,
            "speaker": "技术负责人",
            "text": "可以考虑增加在线提交借用申请的功能",
        },
        {
            "span_id": "span_003",
            "session_id": "test_session",
            "start_ms": 10000,
            "end_ms": 15000,
            "speaker": "产品经理",
            "text": "对，系统应该支持用户自主填写申请表单",
        },
        {
            "span_id": "span_004",
            "session_id": "test_session",
            "start_ms": 15000,
            "end_ms": 20000,
            "speaker": "技术负责人",
            "text": "系统必须在 2 秒内完成审批流程验证，保证用户体验",
        },
        {
            "span_id": "span_005",
            "session_id": "test_session",
            "start_ms": 20000,
            "end_ms": 25000,
            "speaker": "产品经理",
            "text": "还需要考虑权限控制，不同角色看到的内容应该不同",
        },
    ]

    generator = EgoBundleGenerator(max_spans_per_bundle=10)

    # 测试锚点选择
    print("1. 测试锚点选择")
    anchors_all = generator.select_anchors(spans, strategy="all")
    print(f"   全量锚点: {len(anchors_all)} 个")

    anchors_informative = generator.select_anchors(spans, strategy="informative")
    print(f"   信息量锚点: {len(anchors_informative)} 个")
    print()

    # 测试序列窗口 bundle
    print("2. 测试序列窗口 bundle")
    anchor_idx = 2
    bundle = generator.generate_sequence_bundle(spans, anchor_idx, r=2)
    print(f"   锚点索引: {anchor_idx}")
    print(f"   Bundle 包含 {len(bundle['spans'])} 个 span")
    print(f"   短引用: {bundle['span_refs']}")
    print()

    # 打印 bundle 内容示例
    print("3. Bundle 内容示例")
    for i, span in enumerate(bundle["spans"]):
        ref = bundle["span_refs"][i]
        print(f"   {ref}: {span['speaker']} - {span['text'][:50]}...")
    print()


def test_requirements_executor():
    """测试需求执行器"""
    print("=== 测试需求执行器 ===\n")

    # 测试工具定义
    print("1. 工具 Schema")
    schema = RequirementToolDef.get_tool_schema()
    print(json.dumps(schema, indent=2, ensure_ascii=False))
    print()

    # 测试系统提示词
    print("2. 系统提示词")
    system_prompt = RequirementToolDef.get_system_prompt()
    print(system_prompt[:300] + "...")
    print()

    # 测试解析 toolcall
    print("3. 测试 toolcall 解析")
    model_output = """
CALL create_req level="L1" text="提升借用审批效率并降低人工核验成本"
CALL create_req level="L2" text="系统应支持在线提交借用申请"
CALL create_req level="L3" text="系统必须在 2 秒内完成审批流程验证"
"""

    # 注意：这里使用假的 DSN，实际使用时需要真实的数据库连接
    try:
        executor = RequirementsExecutor(dsn="postgresql://user:pass@localhost/test")
    except Exception:
        print("   (跳过数据库连接测试)")
        executor = None

    if executor:
        toolcalls = executor.parse_toolcalls(model_output)
        print(f"   解析到 {len(toolcalls)} 个 toolcall")
        for i, call in enumerate(toolcalls):
            print(f"   {i+1}. {call}")
        print()

        # 测试校验
        print("4. 测试参数校验")
        for i, call in enumerate(toolcalls):
            is_valid, error = executor.validate_toolcall(call)
            status = "✓" if is_valid else "✗"
            print(f"   {status} {call['level']}: {call['text'][:30]}...")
            if error:
                print(f"      错误: {error}")
        print()

        # 测试数量限制
        print("5. 测试数量限制")
        quota_ok, quota_error = executor.check_quota(toolcalls)
        print(f"   数量检查: {'通过' if quota_ok else '失败'}")
        if quota_error:
            print(f"   错误: {quota_error}")
        print()


def test_prompt_building():
    """测试 Prompt 构建"""
    print("=== 测试 Prompt 构建 ===\n")

    bundle = {
        "span_refs": ["S1", "S2", "S3"],
        "spans": [
            {
                "span_id": "span_001",
                "speaker": "产品经理",
                "text": "我们需要提升借用审批效率，降低人工核验成本",
                "start_ms": 0,
                "end_ms": 5000,
            },
            {
                "span_id": "span_002",
                "speaker": "技术负责人",
                "text": "可以考虑增加在线提交借用申请的功能",
                "start_ms": 5000,
                "end_ms": 10000,
            },
            {
                "span_id": "span_003",
                "speaker": "产品经理",
                "text": "对，系统应该支持用户自主填写申请表单",
                "start_ms": 10000,
                "end_ms": 15000,
            },
        ],
    }

    # 模拟 prompt 构建（简化版）
    lines = []
    lines.append("# 上下文片段")
    lines.append("")

    for i, span in enumerate(bundle["spans"]):
        ref = bundle["span_refs"][i]
        speaker = span.get("speaker", "未知")
        text = span.get("text", "")
        start_ms = span.get("start_ms")
        end_ms = span.get("end_ms")

        time_info = ""
        if start_ms is not None and end_ms is not None:
            time_info = f" [{start_ms}ms - {end_ms}ms]"

        lines.append(f"**{ref}**{time_info} {speaker}: {text}")
        lines.append("")

    prompt = "\n".join(lines)
    print(prompt)
    print()


if __name__ == "__main__":
    print("需求抽取功能测试\n")
    print("=" * 60)
    print()

    test_ego_bundle_generator()
    print()
    print("=" * 60)
    print()

    test_requirements_executor()
    print()
    print("=" * 60)
    print()

    test_prompt_building()
    print()
    print("=" * 60)
    print()

    print("测试完成！")
    print()
    print("下一步：")
    print("1. 启动数据库服务")
    print("2. 启动推理后端: cd backend_inference && python main.py")
    print("3. 启动业务后端: cd backend_business && python app.py")
    print("4. 调用 API: POST /api/requirements/extract_l123")
