"""
KB Service - 知识库服务 (基于 LlamaIndex)

负责存放与检索三类知识:
1. PatternIndex: 分解范式库 (来自 enhanced_Cross_dataset.csv 的 label=1 样本)
2. SpecIndex: 规范与模板库 (硬约束条目)
3. NfrIndex: NFR/质量条目库 (非功能需求模板)
"""

from .core import KBService, get_kb_service

__all__ = ["KBService", "get_kb_service"]
