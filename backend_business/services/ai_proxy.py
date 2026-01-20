# 转发请求到 FastAPI :8000 的客户端占位符
# 此模块将来用于封装与推理后端 (FastAPI) 通信的逻辑
import requests
from typing import Any, Dict, List, Optional

from backend_business.config import settings


class AIProxy:
    """
    业务后端调用推理后端（backend_inference）的客户端封装。
    注意：不修改推理后端（尤其是冲突检测）内部结构，仅通过 HTTP 调用。
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def health(self) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/health", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def trace_relation(self, high: str, low: str, max_new_tokens: int = 800) -> Dict[str, Any]:
        resp = requests.post(
            f"{self.base_url}/traceability/relation",
            json={
                "high_level_requirement": high,
                "low_level_requirement": low,
                "max_new_tokens": max_new_tokens,
            },
            timeout=300,  # 5分钟
        )
        resp.raise_for_status()
        return resp.json()

    def trace_batch(
        self,
        highs: List[str],
        lows: List[str],
        max_new_tokens: int = 1600,
    ) -> Dict[str, Any]:
        # 批量分析可能需要更长时间，根据组合数量动态调整超时
        total_combinations = len(highs) * len(lows)
        timeout = max(300, total_combinations * 30)  # 每个组合至少30秒
        timeout = min(timeout, 1800)  # 最多30分钟
        
        resp = requests.post(
            f"{self.base_url}/traceability/batch-relation",
            json={
                "high_level_requirements": highs,
                "low_level_requirements": lows,
                "max_new_tokens": max_new_tokens,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def conflict_check(self, requirement_a: str, requirement_b: str) -> Dict[str, Any]:
        """
        可选：业务层也可代理冲突检测（不改变原冲突代码）。
        """
        resp = requests.post(
            f"{self.base_url}/conflict/check",
            json={"requirement_a": requirement_a, "requirement_b": requirement_b},
            timeout=300,  # 5分钟
        )
        resp.raise_for_status()
        return resp.json()

    def extract_requirements(
        self,
        text: str,
        chunk_size: int = 3600,
        overlap: int = 500,
        clean_model: str = "deepseek-chat",
        extract_model: str = "deepseek-reasoner",
    ) -> Dict[str, Any]:
        """
        调用推理后端进行需求抽取 (L1/L2/L3)
        """
        resp = requests.post(
            f"{self.base_url}/acquisition/extract",
            json={
                "text": text,
                "chunk_size": chunk_size,
                "overlap": overlap,
                "clean_model": clean_model,
                "extract_model": extract_model,
            },
            timeout=900,  # 抽取过程可能较慢，给足超时
        )
        resp.raise_for_status()
        return resp.json()


ai_proxy = AIProxy(settings.INFERENCE_BASE_URL)

# 转发请求到 FastAPI :8000 的客户端占位符
# 此模块将来用于封装与推理后端 (FastAPI) 通信的逻辑
