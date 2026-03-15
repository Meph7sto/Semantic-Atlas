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

from .tool_def import RequirementToolDef


class RequirementsExecutor:
    """
    执行器：解析 toolcall 输出、校验、去重、落库
    支持 create_req 和 update_req 两种操作
    """

    _CALL_LINE_RE = re.compile(
        r'^CALL\s+create_req\s+level="([^"]+)"\s+text="([^"]+)"\s*$'
    )
    _FUZZY_DUP_RATIO = 0.9

    def __init__(self, dsn: str):
        self.dsn = dsn

    def _connect(self) -> psycopg2.extensions.connection:
        return psycopg2.connect(self.dsn)

    def parse_toolcalls(
        self, model_output, include_updates: bool = False
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        解析模型输出的 toolcall 指令

        支持三种格式：
        1. 旧格式（CALL 行）：CALL create_req level="L1" text="..."
        2. DeepSeek API tool_calls 格式：[{"id": ..., "type": "function", "function": {...}}]
        3. 直接的参数字典列表：[{"level": "L1", "text": "..."}]

        Args:
            model_output: 模型输出字符串或工具调用数据
            include_updates: 是否解析 update_req 调用

        Returns:
            (create_calls, update_calls) 分别为创建和更新的调用列表
        """
        import json

        create_calls = []
        update_calls = []

        # 处理 None 或空值
        if model_output is None:
            return create_calls, update_calls

        # 1. DeepSeek API tool_calls 格式（列表）
        if isinstance(model_output, list):
            for call in model_output:
                if isinstance(call, dict):
                    # DeepSeek API 格式: {"id": ..., "type": "function", "function": {"name": ..., "arguments": ...}}
                    if call.get("type") == "function" and "function" in call:
                        func = call["function"]
                        func_name = func.get("name", "")
                        args = func.get("arguments", {})

                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                continue

                        if not isinstance(args, dict):
                            continue

                        if func_name == "create_req":
                            if "level" in args and "text" in args:
                                create_calls.append(
                                    {"level": args["level"], "text": args["text"]}
                                )
                        elif func_name == "update_req" and include_updates:
                            if "req_id" in args and "level" in args and "text" in args:
                                update_calls.append(
                                    {
                                        "req_id": args["req_id"],
                                        "level": args["level"],
                                        "text": args["text"],
                                        "reason": args.get("reason", ""),
                                    }
                                )

                    # 直接的参数字典格式
                    elif "level" in call and "text" in call:
                        if "req_id" in call and include_updates:
                            # update_req 格式
                            update_calls.append(
                                {
                                    "req_id": call["req_id"],
                                    "level": call["level"],
                                    "text": call["text"],
                                    "reason": call.get("reason", ""),
                                }
                            )
                        else:
                            # create_req 格式
                            create_calls.append(
                                {"level": call["level"], "text": call["text"]}
                            )

            return create_calls, update_calls

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
                    create_calls.append({"level": level, "text": text})

        return create_calls, update_calls

    def parse_toolcalls_legacy(self, model_output) -> List[Dict[str, Any]]:
        """
        旧版解析方法，保持向后兼容
        只返回 create_req 调用
        """
        create_calls, _ = self.parse_toolcalls(model_output, include_updates=False)
        return create_calls

    def validate_toolcall(self, call: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        校验单个 create_req toolcall 的参数

        Args:
            call: 工具调用参数

        Returns:
            (是否通过, 错误信息)
        """
        # 1. level 枚举校验
        level = call.get("level", "")
        if level not in RequirementToolDef.LEVEL_ENUM:
            return (
                False,
                f"Invalid level: {level}, must be one of {RequirementToolDef.LEVEL_ENUM}",
            )

        # 2. text 长度校验
        text = call.get("text", "")
        text_len = len(text.strip())
        if text_len < RequirementToolDef.TEXT_MIN_LENGTH:
            return (
                False,
                f"Text too short: {text_len} < {RequirementToolDef.TEXT_MIN_LENGTH}",
            )
        if text_len > RequirementToolDef.TEXT_MAX_LENGTH:
            return (
                False,
                f"Text too long: {text_len} > {RequirementToolDef.TEXT_MAX_LENGTH}",
            )

        return True, None

    def validate_update_call(
        self, call: Dict[str, Any], session_id: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        校验单个 update_req toolcall 的参数

        Args:
            call: 工具调用参数
            session_id: 会话 ID（用于查找需求）

        Returns:
            (是否通过, 错误信息, 完整的 req_id)
        """
        # 1. req_id 存在性校验
        req_id = call.get("req_id", "").strip()
        if not req_id:
            return False, "Missing req_id", None

        # 2. level 枚举校验
        level = call.get("level", "")
        if level not in RequirementToolDef.LEVEL_ENUM:
            return (
                False,
                f"Invalid level: {level}, must be one of {RequirementToolDef.LEVEL_ENUM}",
                None,
            )

        # 3. text 长度校验
        text = call.get("text", "")
        text_len = len(text.strip())
        if text_len < RequirementToolDef.TEXT_MIN_LENGTH:
            return (
                False,
                f"Text too short: {text_len} < {RequirementToolDef.TEXT_MIN_LENGTH}",
                None,
            )
        if text_len > RequirementToolDef.TEXT_MAX_LENGTH:
            return (
                False,
                f"Text too long: {text_len} > {RequirementToolDef.TEXT_MAX_LENGTH}",
                None,
            )

        # 4. 查找完整的 req_id（支持短 ID 匹配）
        full_req_id = self._find_full_req_id(session_id, req_id)
        if not full_req_id:
            return False, f"Requirement not found: {req_id}", None

        return True, None, full_req_id

    def _find_full_req_id(self, session_id: str, short_id: str) -> Optional[str]:
        """
        通过短 ID 查找完整的 req_id

        Args:
            session_id: 会话 ID
            short_id: 短 ID（可能是前缀）

        Returns:
            完整的 req_id，如果找不到或有歧义则返回 None
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 先尝试精确匹配
                cur.execute(
                    """
                    SELECT req_id FROM requirements_l123
                    WHERE session_id = %s AND req_id = %s
                    """,
                    (session_id, short_id),
                )
                row = cur.fetchone()
                if row:
                    return row["req_id"]

                # 再尝试前缀匹配
                cur.execute(
                    """
                    SELECT req_id FROM requirements_l123
                    WHERE session_id = %s AND req_id LIKE %s
                    """,
                    (session_id, f"{short_id}%"),
                )
                rows = cur.fetchall()
                if len(rows) == 1:
                    return rows[0]["req_id"]

        return None

    def update_requirement(
        self,
        session_id: str,
        req_id: str,
        new_level: str,
        new_text: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        更新已存在的需求

        Args:
            session_id: 会话 ID
            req_id: 需求 ID
            new_level: 新的需求层级
            new_text: 新的需求文本
            reason: 更新原因

        Returns:
            更新结果
        """
        result = {
            "success": False,
            "req_id": req_id,
            "old_text": None,
            "old_level": None,
            "new_text": new_text,
            "new_level": new_level,
            "reason": reason,
            "error": None,
        }

        new_text = new_text.strip()
        new_fingerprint = self.compute_fingerprint(session_id, new_level, new_text)

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 先获取原有记录
                cur.execute(
                    """
                    SELECT req_id, session_id, level, text, fingerprint
                    FROM requirements_l123
                    WHERE req_id = %s AND session_id = %s
                    """,
                    (req_id, session_id),
                )
                row = cur.fetchone()

                if not row:
                    result["error"] = f"Requirement not found: {req_id}"
                    return result

                result["old_text"] = row["text"]
                result["old_level"] = row["level"]

                # 执行更新
                try:
                    cur.execute(
                        """
                        UPDATE requirements_l123
                        SET text = %s, fingerprint = %s, level = %s
                        WHERE req_id = %s
                        """,
                        (new_text, new_fingerprint, new_level, req_id),
                    )
                    if cur.rowcount > 0:
                        result["success"] = True
                        conn.commit()
                    else:
                        result["error"] = "Update failed: no rows affected"
                except Exception as e:
                    result["error"] = str(e)

        return result

    def check_quota(
        self, toolcalls: List[Dict[str, Any]]
    ) -> Tuple[bool, Optional[str]]:
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

    def compute_fingerprint(self, session_id: str, level: str, text: str) -> str:
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
        normalized = re.sub(
            r"[，,。.!！？?；;:：\-—（）()\[\]【】\"'`]", "", normalized
        )
        return normalized

    @classmethod
    def _is_fuzzy_duplicate(
        cls, normalized_text: str, existing_texts: List[str]
    ) -> bool:
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
                for idx, call in enumerate(toolcalls):
                    level = call["level"]
                    text = call["text"].strip()
                    normalized_text = self._normalize_similarity_text(text)
                    if self._is_fuzzy_duplicate(
                        normalized_text, existing_texts.get(level, [])
                    ):
                        duplicates += 1
                        continue
                    fingerprint = self.compute_fingerprint(session_id, level, text)
                    req_id = str(uuid.uuid4())

                    savepoint_name = f"req_insert_{idx}"
                    cur.execute(f"SAVEPOINT {savepoint_name}")
                    try:
                        cur.execute(
                            """
                            INSERT INTO requirements_l123 (req_id, session_id, level, text, fingerprint, anchor_span_id, r)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (fingerprint) DO NOTHING
                            """,
                            (
                                req_id,
                                session_id,
                                level,
                                text,
                                fingerprint,
                                anchor_span_id,
                                r,
                            ),
                        )
                        if cur.rowcount > 0:
                            inserted += 1
                            existing_texts.setdefault(level, []).append(normalized_text)
                        else:
                            duplicates += 1
                        cur.execute(f"RELEASE SAVEPOINT {savepoint_name}")
                    except Exception as e:
                        cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                        cur.execute(f"RELEASE SAVEPOINT {savepoint_name}")
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
            if model_output is None or (
                isinstance(model_output, list) and len(model_output) == 0
            ):
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
                invalid_lines = [
                    line for line in non_empty if not self._CALL_LINE_RE.match(line)
                ]
                if invalid_lines:
                    result["status"] = "invalid_format"
                    result["validation_errors"].append(
                        {"error": "Non-CALL output detected", "lines": invalid_lines}
                    )
                    return result

        # 1. 语法解析
        create_calls, _ = self.parse_toolcalls(model_output, include_updates=False)
        result["parsed_count"] = len(create_calls)

        if not create_calls:
            result["status"] = "empty"
            return result

        # 2. 参数校验
        valid_calls = []
        for call in create_calls:
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

    def execute_bundle_with_history(
        self,
        session_id: str,
        anchor_span_id: str,
        r: int,
        model_output,
    ) -> Dict[str, Any]:
        """
        执行带历史感知的需求抽取结果（支持 create_req 和 update_req）

        Args:
            session_id: 会话 ID
            anchor_span_id: 锚点 span ID
            r: 邻域半径
            model_output: 模型输出（tool_calls 列表）

        Returns:
            执行结果，包含创建和更新的统计
        """
        result = {
            "status": "success",
            "parsed_create_count": 0,
            "parsed_update_count": 0,
            "validation_errors": [],
            "quota_error": None,
            "inserted": 0,
            "duplicates": 0,
            "updated": 0,
            "update_errors": [],
            "update_log": [],  # 记录每次更新的详细信息
            "db_errors": [],
        }

        # 0. 格式校验
        if model_output is None or (
            isinstance(model_output, list) and len(model_output) == 0
        ):
            result["status"] = "empty"
            return result

        # 1. 解析 create_req 和 update_req
        create_calls, update_calls = self.parse_toolcalls(
            model_output, include_updates=True
        )
        result["parsed_create_count"] = len(create_calls)
        result["parsed_update_count"] = len(update_calls)

        if not create_calls and not update_calls:
            result["status"] = "empty"
            return result

        # 2. 处理 update_req 调用
        for call in update_calls:
            is_valid, error_msg, full_req_id = self.validate_update_call(
                call, session_id
            )
            if not is_valid:
                result["validation_errors"].append(
                    {
                        "type": "update_req",
                        "call": call,
                        "error": error_msg,
                    }
                )
                continue

            # 执行更新
            update_result = self.update_requirement(
                session_id=session_id,
                req_id=full_req_id,
                new_level=call["level"],
                new_text=call["text"],
                reason=call.get("reason", ""),
            )

            if update_result["success"]:
                result["updated"] += 1
                result["update_log"].append(
                    {
                        "req_id": full_req_id,
                        "old_level": update_result["old_level"],
                        "new_level": update_result["new_level"],
                        "old_text": update_result["old_text"],
                        "new_text": update_result["new_text"],
                        "reason": update_result["reason"],
                    }
                )
            else:
                result["update_errors"].append(
                    {
                        "req_id": call.get("req_id"),
                        "error": update_result["error"],
                    }
                )

        # 3. 处理 create_req 调用
        if create_calls:
            # 参数校验
            valid_create_calls = []
            for call in create_calls:
                is_valid, error_msg = self.validate_toolcall(call)
                if is_valid:
                    valid_create_calls.append(call)
                else:
                    result["validation_errors"].append(
                        {
                            "type": "create_req",
                            "call": call,
                            "error": error_msg,
                        }
                    )

            if valid_create_calls:
                # 数量上限检查
                quota_ok, quota_error = self.check_quota(valid_create_calls)
                if not quota_ok:
                    result["quota_error"] = quota_error
                    # 不完全失败，继续处理已有的更新
                else:
                    # 去重并落库
                    db_result = self.insert_requirements(
                        session_id, anchor_span_id, r, valid_create_calls
                    )
                    result["inserted"] = db_result["inserted"]
                    result["duplicates"] = db_result["duplicates"]
                    result["db_errors"] = db_result["errors"]

        # 4. 确定最终状态
        has_errors = (
            result["validation_errors"]
            or result["update_errors"]
            or result["db_errors"]
            or result["quota_error"]
        )
        has_success = result["inserted"] > 0 or result["updated"] > 0

        if has_success and has_errors:
            result["status"] = "partial_success"
        elif not has_success and has_errors:
            result["status"] = "failed"
        elif not has_success and not has_errors:
            # 所有输入都是重复的
            result["status"] = "empty"

        return result
