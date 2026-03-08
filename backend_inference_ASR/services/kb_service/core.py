"""
KB Service - 核心类实现

负责存放与检索三类知识:
1. PatternIndex: 分解范式库 (来自 enhanced_Cross_dataset.csv 的 label=1 样本)
2. SpecIndex: 规范与模板库 (硬约束条目)
3. NfrIndex: NFR/质量条目库 (非功能需求模板)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

import pandas as pd

# ========================
# LlamaIndex 导入
# ========================
try:
    from llama_index.core import (
        Document,
        Settings,
        StorageContext,
        VectorStoreIndex,
        load_index_from_storage,
    )
    from llama_index.core.node_parser import SimpleNodeParser
    from llama_index.core.schema import TextNode
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    try:
        from llama_index.retrievers.bm25 import BM25Retriever
        BM25_AVAILABLE = True
    except ImportError:
        BM25_AVAILABLE = False

    LLAMAINDEX_AVAILABLE = True
except ImportError:
    LLAMAINDEX_AVAILABLE = False
    BM25_AVAILABLE = False
    print("[KB Service] WARNING: LlamaIndex not installed. KB features disabled.")

from schemas.kb_schemas import EvidenceItem, KBSearchResponse, KBStatus

from .config import DEFAULT_EMBEDDING_MODEL, DEFAULT_PERSIST_DIR
from .definitions import NFR_ENTRIES, SPEC_ENTRIES


class KBService:
    """知识库服务 (基于 LlamaIndex)"""

    def __init__(
        self,
        persist_dir: str = DEFAULT_PERSIST_DIR,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        csv_path: str = "enhanced_Cross_dataset.csv",
    ):
        self.persist_dir = Path(persist_dir)
        self.embedding_model_name = embedding_model
        self.csv_path = csv_path

        # 索引实例
        self._pattern_index: Optional[VectorStoreIndex] = None
        self._spec_index: Optional[VectorStoreIndex] = None
        self._nfr_index: Optional[VectorStoreIndex] = None

        # 节点缓存 (用于 BM25)
        self._pattern_nodes: List[TextNode] = []
        self._spec_nodes: List[TextNode] = []
        self._nfr_nodes: List[TextNode] = []

        # BM25 检索器缓存
        self._bm25_retrievers: Dict[str, Any] = {}

        # Hard negatives
        self._hard_negative_patterns: List[Dict[str, Any]] = []
        self._hard_negative_nodes: List[TextNode] = []
        self._hard_negative_retriever: Optional[Any] = None

        # Evidence 索引
        self._evidence_id_set: Set[str] = set()

        # 嵌入模型
        self._embed_model = None

        # 版本信息
        self._kb_version: str = ""
        self._is_loaded: bool = False

        # 条目计数
        self._pattern_count: int = 0
        self._spec_count: int = 0
        self._nfr_count: int = 0
        self._hard_negative_count: int = 0

    def _get_embed_model(self):
        """懒加载嵌入模型"""
        if not LLAMAINDEX_AVAILABLE:
            raise RuntimeError("LlamaIndex not installed")

        if self._embed_model is None:
            self._embed_model = HuggingFaceEmbedding(
                model_name=self.embedding_model_name
            )
            # 设置全局默认
            Settings.embed_model = self._embed_model

        return self._embed_model

    def _compute_version(
        self,
        pattern_data: List[Dict[str, Any]],
        hard_negatives: List[Dict[str, Any]],
    ) -> str:
        """计算知识库版本 (基于内容 hash)"""

        def _normalize_entries(entries: List[Dict[str, Any]], keys: List[str]) -> List[Dict[str, str]]:
            normalized: List[Dict[str, str]] = []
            for entry in entries:
                normalized.append({k: str(entry.get(k, "")).strip() for k in keys})
            normalized.sort(key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=True))
            return normalized

        content = json.dumps(
            {
                "patterns": _normalize_entries(pattern_data, ["high_text", "low_text"]),
                "hard_negatives": _normalize_entries(hard_negatives, ["high_text", "low_text"]),
                "specs": _normalize_entries(SPEC_ENTRIES, ["id", "text", "category", "source"]),
                "nfrs": _normalize_entries(NFR_ENTRIES, ["id", "text", "nfr_type", "category"]),
                "embedding_model": self.embedding_model_name,
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def _load_pattern_data(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """从 CSV 加载 Pattern 数据 (label=1) 与 hard negatives (label=0)"""
        csv_path = Path(self.csv_path)
        if not csv_path.exists():
            # 尝试从项目根目录查找
            # 注意: 因为文件层级加深了一层,需要多 parent 一次
            project_root = Path(__file__).parent.parent.parent.parent
            csv_path = project_root / self.csv_path

        if not csv_path.exists():
            print(f"[KB Service] WARNING: CSV not found at {csv_path}")
            return [], []

        try:
            # 尝试多种编码
            for encoding in ["utf-8", "latin-1", "cp1252"]:
                try:
                    df = pd.read_csv(csv_path, encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                print(f"[KB Service] ERROR: Cannot decode CSV file")
                return [], []

            patterns = []
            hard_negatives = []

            high_col = (
                "high_requeriment"
                if "high_requeriment" in df.columns
                else "high_requirement"
            )
            low_col = (
                "low_requeriment" if "low_requeriment" in df.columns else "low_requirement"
            )

            for idx, row in df.iterrows():
                high_text = str(row.get(high_col, "")).strip()
                low_text = str(row.get(low_col, "")).strip()
                label = int(row.get("label", 1)) if "label" in df.columns else 1

                if not high_text or not low_text:
                    continue

                entry = {
                    "id": f"pattern-{idx:04d}",
                    "high_text": high_text,
                    "low_text": low_text,
                    "text": f"高层需求: {high_text}\n低层需求: {low_text}",
                }

                if label == 1:
                    patterns.append(entry)
                elif label == 0:
                    hard_negatives.append(
                        {
                            **entry,
                            "id": f"hard-negative-{idx:04d}",
                        }
                    )

            print(
                f"[KB Service] Loaded {len(patterns)} patterns and {len(hard_negatives)} hard negatives from CSV"
            )
            return patterns, hard_negatives

        except Exception as e:
            print(f"[KB Service] ERROR loading CSV: {e}")
            return [], []

    def _build_pattern_index(self, patterns: List[Dict]) -> VectorStoreIndex:
        """构建 Pattern 索引"""
        nodes = []
        for p in patterns:
            node = TextNode(
                text=p["text"],
                id_=p["id"],
                metadata={
                    "kb_type": "pattern",
                    "high_text": p["high_text"],
                    "low_text": p["low_text"],
                },
            )
            nodes.append(node)

        self._pattern_nodes = nodes
        return VectorStoreIndex(nodes, embed_model=self._get_embed_model())

    def _build_spec_index(self) -> VectorStoreIndex:
        """构建 Spec 索引"""
        nodes = []
        for entry in SPEC_ENTRIES:
            node = TextNode(
                text=entry["text"],
                id_=entry["id"],
                metadata={
                    "kb_type": "spec",
                    "category": entry.get("category", ""),
                    "source": entry.get("source", ""),
                },
            )
            nodes.append(node)

        self._spec_nodes = nodes
        return VectorStoreIndex(nodes, embed_model=self._get_embed_model())

    def _build_nfr_index(self) -> VectorStoreIndex:
        """构建 NFR 索引"""
        nodes = []
        for entry in NFR_ENTRIES:
            node = TextNode(
                text=entry["text"],
                id_=entry["id"],
                metadata={
                    "kb_type": "nfr",
                    "nfr_type": entry.get("nfr_type", ""),
                    "category": entry.get("category", ""),
                },
            )
            nodes.append(node)

        self._nfr_nodes = nodes
        return VectorStoreIndex(nodes, embed_model=self._get_embed_model())

    def _build_hard_negative_nodes(self, hard_negatives: List[Dict[str, Any]]) -> None:
        """构建 hard negatives 节点列表 (仅用于检索评估/过滤)"""
        nodes = []
        for entry in hard_negatives:
            node = TextNode(
                text=entry["text"],
                id_=entry["id"],
                metadata={
                    "kb_type": "hard_negative",
                    "high_text": entry.get("high_text", ""),
                    "low_text": entry.get("low_text", ""),
                },
            )
            nodes.append(node)
        self._hard_negative_nodes = nodes

    def _refresh_evidence_id_set(self) -> None:
        evidence_ids: Set[str] = set()
        for nodes in (self._pattern_nodes, self._spec_nodes, self._nfr_nodes):
            for node in nodes:
                node_id = node.id_ or getattr(node, "node_id", None) or ""
                if node_id:
                    evidence_ids.add(node_id)
        self._evidence_id_set = evidence_ids

    def _persist_hard_negatives(
        self, pattern_dir: Path, hard_negatives: List[Dict[str, Any]]
    ) -> None:
        hard_negative_file = pattern_dir / "hard_negatives.json"
        with open(hard_negative_file, "w", encoding="utf-8") as f:
            json.dump(hard_negatives, f, ensure_ascii=True, indent=2)

    def _load_hard_negatives(self, pattern_dir: Path) -> List[Dict[str, Any]]:
        hard_negative_file = pattern_dir / "hard_negatives.json"
        if not hard_negative_file.exists():
            return []
        try:
            with open(hard_negative_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception as e:
            print(f"[KB Service] ERROR loading hard negatives: {e}")
        return []

    def _load_nodes_from_index(self, index: VectorStoreIndex) -> List[TextNode]:
        nodes: List[TextNode] = []
        try:
            if hasattr(index, "docstore"):
                docstore = index.docstore
                if hasattr(docstore, "get_all_nodes"):
                    stored = docstore.get_all_nodes()
                    if isinstance(stored, dict):
                        nodes = list(stored.values())
                    elif isinstance(stored, list):
                        nodes = stored
                elif hasattr(docstore, "docs"):
                    nodes = list(docstore.docs.values())
        except Exception:
            return []
        return nodes

    def _get_bm25_retriever(
        self, kb_type: str, index: VectorStoreIndex, top_k: int
    ) -> Optional[Any]:
        if not BM25_AVAILABLE:
            return None

        retriever = self._bm25_retrievers.get(kb_type)
        if retriever is None:
            nodes = []
            if kb_type == "pattern":
                nodes = self._pattern_nodes or self._load_nodes_from_index(index)
                self._pattern_nodes = nodes
            elif kb_type == "spec":
                nodes = self._spec_nodes or self._load_nodes_from_index(index)
                self._spec_nodes = nodes
            elif kb_type == "nfr":
                nodes = self._nfr_nodes or self._load_nodes_from_index(index)
                self._nfr_nodes = nodes

            if not nodes:
                return None

            try:
                retriever = BM25Retriever.from_defaults(
                    nodes=nodes, similarity_top_k=top_k
                )
            except Exception:
                try:
                    retriever = BM25Retriever.from_defaults(
                        docstore=index.docstore, similarity_top_k=top_k
                    )
                except Exception as e:
                    print(f"[KB Service] ERROR initializing BM25 retriever: {e}")
                    return None

            self._bm25_retrievers[kb_type] = retriever

        if hasattr(retriever, "similarity_top_k"):
            retriever.similarity_top_k = top_k

        return retriever

    def _get_hard_negative_retriever(self, top_k: int) -> Optional[Any]:
        if not BM25_AVAILABLE or not self._hard_negative_nodes:
            return None

        if self._hard_negative_retriever is None:
            try:
                self._hard_negative_retriever = BM25Retriever.from_defaults(
                    nodes=self._hard_negative_nodes, similarity_top_k=top_k
                )
            except Exception as e:
                print(f"[KB Service] ERROR initializing hard negative retriever: {e}")
                return None

        if hasattr(self._hard_negative_retriever, "similarity_top_k"):
            self._hard_negative_retriever.similarity_top_k = top_k

        return self._hard_negative_retriever

    def _merge_retrieval_results(
        self,
        vector_results: List[Any],
        bm25_results: List[Any],
        top_k: int,
    ) -> List[Tuple[TextNode, float, float, float]]:
        merged: Dict[str, Dict[str, Any]] = {}

        def _node_id(node: Any) -> str:
            return (
                getattr(node, "id_", None)
                or getattr(node, "node_id", None)
                or getattr(node, "id", None)
                or "unknown"
            )

        for result in vector_results or []:
            node = result.node
            node_id = _node_id(node)
            merged[node_id] = {
                "node": node,
                "vector_score": float(result.score or 0.0),
                "bm25_score": 0.0,
            }

        for result in bm25_results or []:
            node = result.node
            node_id = _node_id(node)
            entry = merged.get(node_id)
            if entry is None:
                entry = {
                    "node": node,
                    "vector_score": 0.0,
                    "bm25_score": 0.0,
                }
                merged[node_id] = entry
            entry["bm25_score"] = float(result.score or 0.0)

        max_vector = max((item["vector_score"] for item in merged.values()), default=0.0)
        max_bm25 = max((item["bm25_score"] for item in merged.values()), default=0.0)

        combined_results: List[Tuple[TextNode, float, float, float]] = []
        for entry in merged.values():
            vector_score = entry["vector_score"]
            bm25_score = entry["bm25_score"]

            vector_norm = vector_score / max_vector if max_vector > 0 else 0.0
            bm25_norm = bm25_score / max_bm25 if max_bm25 > 0 else 0.0

            if vector_score > 0 and bm25_score > 0:
                combined_score = 0.6 * vector_norm + 0.4 * bm25_norm
            elif vector_score > 0:
                combined_score = vector_norm
            else:
                combined_score = bm25_norm

            combined_results.append(
                (entry["node"], combined_score, vector_score, bm25_score)
            )

        combined_results.sort(key=lambda item: item[1], reverse=True)
        return combined_results[:top_k]

    def build_indexes(self) -> str:
        """构建并持久化所有索引"""
        if not LLAMAINDEX_AVAILABLE:
            raise RuntimeError("LlamaIndex not installed")

        print("[KB Service] Building indexes...")

        self._bm25_retrievers = {}
        self._hard_negative_retriever = None

        # 加载 Pattern 数据
        patterns, hard_negatives = self._load_pattern_data()
        self._pattern_count = len(patterns)
        self._hard_negative_patterns = hard_negatives
        self._hard_negative_count = len(hard_negatives)
        self._spec_count = len(SPEC_ENTRIES)
        self._nfr_count = len(NFR_ENTRIES)

        # 计算版本
        self._kb_version = self._compute_version(patterns, hard_negatives)
        print(f"[KB Service] Building KB version: {self._kb_version}")

        # 构建索引
        self._pattern_index = self._build_pattern_index(patterns)
        self._spec_index = self._build_spec_index()
        self._nfr_index = self._build_nfr_index()
        self._build_hard_negative_nodes(hard_negatives)
        self._refresh_evidence_id_set()

        # 持久化
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        pattern_dir = self.persist_dir / "pattern"
        spec_dir = self.persist_dir / "spec"
        nfr_dir = self.persist_dir / "nfr"

        self._pattern_index.storage_context.persist(persist_dir=str(pattern_dir))
        self._spec_index.storage_context.persist(persist_dir=str(spec_dir))
        self._nfr_index.storage_context.persist(persist_dir=str(nfr_dir))

        self._persist_hard_negatives(pattern_dir, hard_negatives)

        # 保存版本信息
        version_file = self.persist_dir / "version.json"
        with open(version_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "kb_version": self._kb_version,
                    "pattern_count": self._pattern_count,
                    "spec_count": self._spec_count,
                    "nfr_count": self._nfr_count,
                    "hard_negative_count": self._hard_negative_count,
                    "embedding_model": self.embedding_model_name,
                },
                f,
                indent=2,
            )

        self._is_loaded = True
        print(f"[KB Service] Indexes built and persisted to {self.persist_dir}")
        return self._kb_version

    def load_indexes(self) -> bool:
        """从持久化存储加载索引"""
        if not LLAMAINDEX_AVAILABLE:
            raise RuntimeError("LlamaIndex not installed")

        self._bm25_retrievers = {}
        self._hard_negative_retriever = None

        version_file = self.persist_dir / "version.json"
        pattern_dir = self.persist_dir / "pattern"
        spec_dir = self.persist_dir / "spec"
        nfr_dir = self.persist_dir / "nfr"

        # 检查是否存在持久化索引
        if not all(
            [
                version_file.exists(),
                pattern_dir.exists(),
                spec_dir.exists(),
                nfr_dir.exists(),
            ]
        ):
            print("[KB Service] No persisted indexes found, need to build")
            return False

        try:
            # 读取版本信息
            with open(version_file, "r", encoding="utf-8") as f:
                version_info = json.load(f)

            self._kb_version = version_info.get("kb_version", "unknown")
            self._pattern_count = version_info.get("pattern_count", 0)
            self._spec_count = version_info.get("spec_count", 0)
            self._nfr_count = version_info.get("nfr_count", 0)
            self._hard_negative_count = version_info.get("hard_negative_count", 0)

            print(f"[KB Service] Loading indexes, version: {self._kb_version}")

            # 设置嵌入模型
            self._get_embed_model()

            # 加载索引
            pattern_storage = StorageContext.from_defaults(persist_dir=str(pattern_dir))
            self._pattern_index = load_index_from_storage(pattern_storage)

            spec_storage = StorageContext.from_defaults(persist_dir=str(spec_dir))
            self._spec_index = load_index_from_storage(spec_storage)

            nfr_storage = StorageContext.from_defaults(persist_dir=str(nfr_dir))
            self._nfr_index = load_index_from_storage(nfr_storage)

            self._pattern_nodes = self._load_nodes_from_index(self._pattern_index)
            self._spec_nodes = self._load_nodes_from_index(self._spec_index)
            self._nfr_nodes = self._load_nodes_from_index(self._nfr_index)

            self._refresh_evidence_id_set()

            self._hard_negative_patterns = self._load_hard_negatives(pattern_dir)
            self._hard_negative_count = len(self._hard_negative_patterns)
            self._build_hard_negative_nodes(self._hard_negative_patterns)

            self._is_loaded = True
            print(f"[KB Service] Indexes loaded successfully")
            return True

        except Exception as e:
            print(f"[KB Service] ERROR loading indexes: {e}")
            return False

    def ensure_loaded(self) -> str:
        """确保索引已加载,如果不存在则构建"""
        if self._is_loaded:
            return self._kb_version

        if not self.load_indexes():
            return self.build_indexes()

        return self._kb_version

    def search(
        self,
        query: str,
        kb_type: Literal["pattern", "spec", "nfr", "all"] = "all",
        top_k: int = 5,
        filters: Optional[Dict[str, str]] = None,
    ) -> KBSearchResponse:
        """统一检索入口"""
        if not self._is_loaded:
            self.ensure_loaded()

        items: List[EvidenceItem] = []
        total_searched = 0

        # 确定要检索的索引
        indexes_to_search: List[Tuple[str, VectorStoreIndex, int]] = []

        if kb_type in ("pattern", "all") and self._pattern_index:
            indexes_to_search.append(("pattern", self._pattern_index, self._pattern_count))
        if kb_type in ("spec", "all") and self._spec_index:
            indexes_to_search.append(("spec", self._spec_index, self._spec_count))
        if kb_type in ("nfr", "all") and self._nfr_index:
            indexes_to_search.append(("nfr", self._nfr_index, self._nfr_count))

        for idx_type, index, count in indexes_to_search:
            total_searched += count

            try:
                vector_results = []
                bm25_results = []

                retriever = index.as_retriever(similarity_top_k=top_k)
                vector_results = retriever.retrieve(query)

                bm25_retriever = self._get_bm25_retriever(idx_type, index, top_k)
                if bm25_retriever:
                    bm25_results = bm25_retriever.retrieve(query)

                combined_results = self._merge_retrieval_results(
                    vector_results, bm25_results, top_k
                )

                hard_negative_max_score = 0.0
                if idx_type == "pattern":
                    hard_negative_retriever = self._get_hard_negative_retriever(3)
                    if hard_negative_retriever:
                        hard_negative_results = hard_negative_retriever.retrieve(query)
                        hard_negative_max_score = max(
                            (
                                float(result.score or 0.0)
                                for result in hard_negative_results
                            ),
                            default=0.0,
                        )

                for node, combined_score, vector_score, bm25_score in combined_results:
                    # 应用过滤器
                    if filters:
                        skip = False
                        for k, v in filters.items():
                            if node.metadata.get(k, "") != v:
                                skip = True
                                break
                        if skip:
                            continue

                    if (
                        idx_type == "pattern"
                        and hard_negative_max_score > 0
                        and bm25_score > 0
                        and bm25_score <= hard_negative_max_score * 0.9
                    ):
                        continue

                    metadata = dict(node.metadata) if node.metadata else {}
                    if bm25_results:
                        metadata["retrieval_mode"] = "hybrid"
                        metadata["score_vector"] = float(vector_score)
                        metadata["score_bm25"] = float(bm25_score)
                    else:
                        metadata["retrieval_mode"] = "vector"
                    if idx_type == "pattern" and hard_negative_max_score > 0:
                        metadata["hard_negative_max_score"] = float(
                            hard_negative_max_score
                        )

                    item = EvidenceItem(
                        evidence_id=node.id_ or f"{idx_type}-unknown",
                        kb_type=idx_type,  # type: ignore
                        text=node.text,
                        score=float(combined_score),
                        metadata=metadata,
                    )
                    items.append(item)

            except Exception as e:
                print(f"[KB Service] ERROR searching {idx_type}: {e}")

        # 按分数排序并截取 top_k
        items.sort(key=lambda x: x.score, reverse=True)
        items = items[:top_k]

        return KBSearchResponse(
            items=items,
            kb_version=self._kb_version,
            total_searched=total_searched,
        )

    def get_status(self) -> KBStatus:
        """获取知识库状态"""
        return KBStatus(
            is_loaded=self._is_loaded,
            kb_version=self._kb_version,
            pattern_count=self._pattern_count,
            spec_count=self._spec_count,
            nfr_count=self._nfr_count,
            hard_negative_count=self._hard_negative_count,
            index_path=str(self.persist_dir),
        )

    def evidence_exists(self, evidence_id: str) -> bool:
        """检查 evidence_id 是否存在于 KB 中"""
        if not self._is_loaded:
            self.ensure_loaded()
        return evidence_id in self._evidence_id_set


# ========================
# 全局单例
# ========================
_kb_service_instance: Optional[KBService] = None


def get_kb_service() -> KBService:
    """获取 KB Service 单例"""
    global _kb_service_instance
    if _kb_service_instance is None:
        _kb_service_instance = KBService()
    return _kb_service_instance
