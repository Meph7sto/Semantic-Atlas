from schemas.conflict_report import ConflictCheckResponse
from core.engine.remote.deepseek import DEFAULT_DEEPSEEK_MODEL


# 定义系统提示词，用于指导模型进行冲突检测
SYSTEM_PROMPT_CONFLICT = """你是一个严格的系统需求分析专家。
你的任务是判断"需求A"和"需求B"是否存在实质性的逻辑冲突。

判断规则：
1. 冲突：指两个需求无法同时被满足（例如 A要求"响应时间<1s"，B要求"响应时间>2s"；或者 A要求"黑色背景"，B要求"白色背景"）。
2. 不冲突：指两个需求兼容、一致、或者属于不同维度（例如 A要求"快"，B要求"快"；或者 A要求"界面美观"，B要求"功能稳定"）。
3. 需求内容相同或相似，视为"不冲突"。

输出格式：
- 如果冲突，请直接以"冲突"开头，后跟简短原因。
- 如果不冲突，请直接以"不冲突"开头。
"""


class ConflictService:
    """
    需求冲突检测服务
    负责处理需求冲突分析的核心业务逻辑
    """

    def __init__(self, model_engine):
        """
        初始化冲突检测服务
        
        Args:
            model_engine: 模型引擎实例
        """
        self.model_engine = model_engine

    def check_conflict(
        self,
        requirement_a: str,
        requirement_b: str,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        use_thinking_mode: bool = True,
    ) -> ConflictCheckResponse:
        """
        专门分析两个需求是否存在潜在冲突
        
        Args:
            requirement_a: 第一个需求描述
            requirement_b: 第二个需求描述
            
        Returns:
            ConflictCheckResponse: 包含冲突检测结果的响应对象
        """
        # 构造用户提示词
        prompt = f"需求A：{requirement_a}\n需求B：{requirement_b}\n这两个需求冲突吗？给出原因"
        
        # 使用共享的模型引擎生成回答
        answer = self.model_engine.generate(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT_CONFLICT,
            max_new_tokens=2048,
            model=model,
            thinking_enabled=use_thinking_mode,
        )
        
        # 鲁棒的解析逻辑
        clean_answer = answer.strip()
        if clean_answer.startswith("不冲突"):
            is_conflict = False
        elif clean_answer.startswith("冲突"):
            is_conflict = True
        else:
            # 回退方案: 查找关键词
            if "不冲突" in clean_answer:
                is_conflict = False
            elif "冲突" in clean_answer:
                is_conflict = True
            else:
                is_conflict = False  # 默认的安全假设
        
        return ConflictCheckResponse(
            is_conflict=is_conflict,
            raw_response=answer
        )

    def check_conflict_stream(
        self,
        requirement_a: str,
        requirement_b: str,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        use_thinking_mode: bool = True,
    ):
        """
        流式分析两个需求是否存在潜在冲突
        Yields:
            str: JSON strings representing tokens or final result
        """
        import json
        
        # 构造用户提示词
        prompt = f"需求A：{requirement_a}\n需求B：{requirement_b}\n这两个需求冲突吗？"
        
        # 获取流式生成器
        stream = self.model_engine.generate_stream(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT_CONFLICT,
            max_new_tokens=2048,
            model=model,
            thinking_enabled=use_thinking_mode,
        )
        
        full_response = ""
        
        # 逐个 Yield Token
        # 逐个 Yield Token
        for chunk in stream:
            # 兼容旧版(str)和新版(dict)
            if isinstance(chunk, dict):
                msg_type = chunk.get("type", "content")
                content = chunk.get("delta", "")
                
                if msg_type == "thinking":
                    # 直接透传思维链
                    yield json.dumps({"type": "thinking", "content": content}, ensure_ascii=False) + "\n"
                else:
                    # 内容部分，累积并输出
                    full_response += content
                    yield json.dumps({"type": "token", "content": content}, ensure_ascii=False) + "\n"
            else:
                # 假设是字符串
                token = str(chunk)
                full_response += token
                yield json.dumps({"type": "token", "content": token}, ensure_ascii=False) + "\n"
            
        # 鲁棒的解析逻辑 (复用 check_conflict 的逻辑)
        clean_answer = full_response.strip()
        if clean_answer.startswith("不冲突"):
            is_conflict = False
        elif clean_answer.startswith("冲突"):
            is_conflict = True
        else:
            # 回退方案
            if "不冲突" in clean_answer:
                is_conflict = False
            elif "冲突" in clean_answer:
                is_conflict = True
            else:
                is_conflict = False
        
        result = ConflictCheckResponse(
            is_conflict=is_conflict,
            raw_response=full_response
        )
        
        # Yield 最终结果
        yield json.dumps({"type": "result", "data": result.model_dump()}, ensure_ascii=False) + "\n"
