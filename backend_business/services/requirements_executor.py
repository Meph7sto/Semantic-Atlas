"""
需求抽取执行器
负责解析 toolcall 输出、校验参数、去重和落库
"""
import difflib
import hashlib
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor


class RequirementToolDef:
    """
    create_req 工具定义与约束规则
    """

    LEVEL_ENUM = {"L1", "L2", "L3"}
    TEXT_MIN_LENGTH = 10
    TEXT_MAX_LENGTH = 500

    # 每个 EgoBundle 的产出上限
    QUOTA_PER_BUNDLE = {
        "L1": 2,
        "L2": 5,
        "L3": 8,
    }

    # L3 引导关键词（优先使用，但不强制）
    L3_KEYWORDS = ["系统必须", "应当", "shall", "must", "should"]

    @classmethod
    def get_tool_schema(cls) -> Dict[str, Any]:
        """
        返回 create_req 工具的 JSON Schema
        用于传递给大模型，符合 DeepSeek API tool call 格式
        参考: https://api-docs.deepseek.com/zh-cn/guides/tool_calls
        """
        return {
            "type": "function",
            "function": {
                "name": "create_req",
                "description": "创建一条 L1/L2/L3 需求条目。L1为业务目标，L2为功能需求，L3为系统需求（建议使用'系统必须/应当/shall/must/should'等可验证措辞）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "level": {
                            "type": "string",
                            "enum": ["L1", "L2", "L3"],
                            "description": "需求层级：L1（业务目标）、L2（功能需求）、L3（系统需求）",
                        },
                        "text": {
                            "type": "string",
                            "description": "需求文本，应当简洁明确地描述需求内容",
                        },
                    },
                    "required": ["level", "text"],
                    "additionalProperties": False,
                },
            },
        }

    @classmethod
    def get_tools_list(cls) -> List[Dict[str, Any]]:
        """
        返回工具列表，用于 DeepSeek API tool call
        """
        return [cls.get_tool_schema()]

    @classmethod
    def get_system_prompt(cls) -> str:
        """
        返回系统提示词，用于 tool call 模式下的需求分析
        """
        return f"""你是一个专业的需求分析助手。请根据提供的上下文片段，使用 create_req 工具抽取需求条目。

**需求层级说明：**
- L1：业务目标、宏观愿景（如"提升借用审批效率并降低人工核验成本"）
- L2：功能需求、用户故事（如"系统应支持在线提交借用申请"）
- L3：系统需求、技术约束（如"系统必须在 2 秒内完成审批流程验证"）
  - L3 可优先覆盖性能/稳定性/安全/一致性/容量/接口边界等可验证约束

**约束规则：**
1. level 必须属于 L1、L2、L3 之一。
2. text 非空，长度限制 {cls.TEXT_MIN_LENGTH}-{cls.TEXT_MAX_LENGTH} 字。
3. 产出上限：L1 <= {cls.QUOTA_PER_BUNDLE['L1']}，L2 <= {cls.QUOTA_PER_BUNDLE['L2']}，L3 <= {cls.QUOTA_PER_BUNDLE['L3']}。
4. L3 建议使用"系统必须/应当/shall/must/should"等可验证措辞，但不强制；更鼓励明确的系统能力、质量指标、边界或约束。
5. 若上下文不足以形成某层需求，该层可为空，但不得编造与输入无关的需求。
"""


class RequirementsExecutor:
    """
    执行器：解析 toolcall 输出、校验、去重、落库
    """

    _CALL_LINE_RE = re.compile(
        r'^CALL\s+create_req\s+level="([^"]+)"\s+text="([^"]+)"\s*$'
    )
    _FUZZY_DUP_RATIO = 0.9

    def __init__(self, dsn: str):
        self.dsn = dsn

    def _connect(self) -> psycopg2.extensions.connection:
        return psycopg2.connect(self.dsn)

    def parse_toolcalls(self, model_output) -> List[Dict[str, Any]]:
        """
        解析模型输出的 toolcall 指令

        支持三种格式：
        1. 旧格式（CALL 行）：CALL create_req level="L1" text="..."
        2. DeepSeek API tool_calls 格式：[{"id": ..., "type": "function", "function": {...}}]
        3. 直接的参数字典列表：[{"level": "L1", "text": "..."}]

        Args:
            model_output: 模型输出字符串或工具调用数据

        Returns:
            解析后的工具调用列表 [{"level": "L1", "text": "..."}]
        """
        import json
        toolcalls = []

        # 处理 None 或空值
        if model_output is None:
            return toolcalls

        # 1. DeepSeek API tool_calls 格式（列表）
        if isinstance(model_output, list):
            for call in model_output:
                if isinstance(call, dict):
                    # DeepSeek API 格式: {"id": ..., "type": "function", "function": {"name": ..., "arguments": ...}}
                    if call.get("type") == "function" and "function" in call:
                        func = call["function"]
                        if func.get("name") == "create_req":
                            # arguments 可能是字符串或字典
                            args = func.get("arguments", {})
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except json.JSONDecodeError:
                                    continue
                            if isinstance(args, dict) and "level" in args and "text" in args:
                                toolcalls.append({"level": args["level"], "text": args["text"]})
                    # 直接的参数字典格式: {"level": "L1", "text": "..."}
                    elif "level" in call and "text" in call:
                        toolcalls.append({"level": call["level"], "text": call["text"]})
            return toolcalls

        # 2. 字符串格式 - 旧格式（CALL 行）
        if isinstance(model_output, str):
            for line in model_output.splitlines():
                line = line.strip()
                if not line:
                    continue
                match = self._CALL_LINE_RE.match(line)
                if match:
                    level = match.group(1)
                    text = match.group(2)
                    toolcalls.append({"level": level, "text": text})

        return toolcalls

    def validate_toolcall(self, call: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        校验单个 toolcall 的参数

        Args:
            call: 工具调用参数

        Returns:
            (是否通过, 错误信息)
        """
        # 1. level 枚举校验
        level = call.get("level", "")
        if level not in RequirementToolDef.LEVEL_ENUM:
            return False, f"Invalid level: {level}, must be one of {RequirementToolDef.LEVEL_ENUM}"

        # 2. text 长度校验
        text = call.get("text", "")
        text_len = len(text.strip())
        if text_len < RequirementToolDef.TEXT_MIN_LENGTH:
            return False, f"Text too short: {text_len} < {RequirementToolDef.TEXT_MIN_LENGTH}"
        if text_len > RequirementToolDef.TEXT_MAX_LENGTH:
            return False, f"Text too long: {text_len} > {RequirementToolDef.TEXT_MAX_LENGTH}"

        return True, None

    def check_quota(self, toolcalls: List[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
        """
        检查数量上限

        Args:
            toolcalls: 工具调用列表

        Returns:
            (是否通过, 错误信息)
        """
        level_counts = {"L1": 0, "L2": 0, "L3": 0}
        for call in toolcalls:
            level = call.get("level")
            if level in level_counts:
                level_counts[level] += 1

        for level, count in level_counts.items():
            quota = RequirementToolDef.QUOTA_PER_BUNDLE[level]
            if count > quota:
                return False, f"Too many {level} requirements: {count} > {quota}"

        return True, None

    def compute_fingerprint(
        self, session_id: str, level: str, text: str
    ) -> str:
        """
        计算需求指纹用于去重

        Args:
            session_id: 会话 ID
            level: 需求层级
            text: 需求文本（会归一化）

        Returns:
            SHA256 指纹
        """
        # 归一化：去除多余空白、转小写
        normalized = re.sub(r"\s+", " ", text.strip()).lower()
        raw = f"{session_id}|{level}|{normalized}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_similarity_text(text: str) -> str:
        normalized = text.strip().lower()
        normalized = re.sub(r"\s+", "", normalized)
        normalized = re.sub(r"[，,。.!！？?；;:：\-—（）()\[\]【】“”\"'`]", "", normalized)
        return normalized

    @classmethod
    def _is_fuzzy_duplicate(cls, normalized_text: str, existing_texts: List[str]) -> bool:
        if not normalized_text or not existing_texts:
            return False
        for existing in existing_texts:
            if normalized_text == existing:
                return True
            ratio = difflib.SequenceMatcher(None, normalized_text, existing).ratio()
            if ratio >= cls._FUZZY_DUP_RATIO:
                return True
        return False

    def _load_existing_texts(
        self, cur: RealDictCursor, session_id: str
    ) -> Dict[str, List[str]]:
        cur.execute(
            """
            SELECT level, text
            FROM requirements_l123
            WHERE session_id = %s
            """,
            (session_id,),
        )
        existing: Dict[str, List[str]] = {}
        for row in cur.fetchall():
            level = row.get("level")
            text = row.get("text", "")
            if not level:
                continue
            existing.setdefault(level, []).append(self._normalize_similarity_text(text))
        return existing

    def insert_requirements(
        self,
        session_id: str,
        anchor_span_id: str,
        r: int,
        toolcalls: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        批量插入需求，自动去重

        Args:
            session_id: 会话 ID
            anchor_span_id: 锚点 span ID
            r: 邻域半径
            toolcalls: 已校验的工具调用列表

        Returns:
            执行结果统计
        """
        inserted = 0
        duplicates = 0
        errors = []

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                existing_texts = self._load_existing_texts(cur, session_id)
                for call in toolcalls:
                    level = call["level"]
                    text = call["text"].strip()
                    normalized_text = self._normalize_similarity_text(text)
                    if self._is_fuzzy_duplicate(normalized_text, existing_texts.get(level, [])):
                        duplicates += 1
                        continue
                    fingerprint = self.compute_fingerprint(session_id, level, text)
                    req_id = str(uuid.uuid4())

                    try:
                        cur.execute(
                            """
                            INSERT INTO requirements_l123 (req_id, session_id, level, text, fingerprint, anchor_span_id, r)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (fingerprint) DO NOTHING
                            """,
                            (req_id, session_id, level, text, fingerprint, anchor_span_id, r),
                        )
                        if cur.rowcount > 0:
                            inserted += 1
                            existing_texts.setdefault(level, []).append(normalized_text)
                        else:
                            duplicates += 1
                    except Exception as e:
                        errors.append({"call": call, "error": str(e)})

        return {
            "inserted": inserted,
            "duplicates": duplicates,
            "errors": errors,
        }

    def execute_bundle(
        self,
        session_id: str,
        anchor_span_id: str,
        r: int,
        model_output,
        use_toolcall_format: bool = False,
    ) -> Dict[str, Any]:
        """
        执行单个 EgoBundle 的需求抽取结果

        Args:
            session_id: 会话 ID
            anchor_span_id: 锚点 span ID
            r: 邻域半径
            model_output: 模型输出（字符串或 tool_calls 列表）
            use_toolcall_format: 是否使用 DeepSeek API tool_call 格式

        Returns:
            执行结果
        """
        result = {
            "status": "success",
            "parsed_count": 0,
            "validation_errors": [],
            "quota_error": None,
            "inserted": 0,
            "duplicates": 0,
            "db_errors": [],
        }

        # 0. 格式校验 - 根据 use_toolcall_format 区分处理
        if use_toolcall_format:
            # tool_call 格式：model_output 应该是 tool_calls 列表
            if model_output is None or (isinstance(model_output, list) and len(model_output) == 0):
                result["status"] = "empty"
                return result
        else:
            # 旧格式：严格校验每行必须是 CALL create_req
            if isinstance(model_output, str):
                lines = [line.strip() for line in model_output.splitlines()]
                non_empty = [line for line in lines if line]
                if not non_empty:
                    result["status"] = "empty"
                    return result
                invalid_lines = [line for line in non_empty if not self._CALL_LINE_RE.match(line)]
                if invalid_lines:
                    result["status"] = "invalid_format"
                    result["validation_errors"].append(
                        {"error": "Non-CALL output detected", "lines": invalid_lines}
                    )
                    return result

        # 1. 语法解析
        toolcalls = self.parse_toolcalls(model_output)
        result["parsed_count"] = len(toolcalls)

        if not toolcalls:
            result["status"] = "empty"
            return result

        # 2. 参数校验
        valid_calls = []
        for call in toolcalls:
            is_valid, error_msg = self.validate_toolcall(call)
            if is_valid:
                valid_calls.append(call)
            else:
                result["validation_errors"].append({"call": call, "error": error_msg})

        if not valid_calls:
            result["status"] = "validation_failed"
            return result

        # 3. 数量上限检查
        quota_ok, quota_error = self.check_quota(valid_calls)
        if not quota_ok:
            result["status"] = "quota_exceeded"
            result["quota_error"] = quota_error
            return result

        # 4. 去重并落库
        db_result = self.insert_requirements(session_id, anchor_span_id, r, valid_calls)
        result["inserted"] = db_result["inserted"]
        result["duplicates"] = db_result["duplicates"]
        result["db_errors"] = db_result["errors"]

        if db_result["errors"]:
            result["status"] = "partial_success"

        return result
