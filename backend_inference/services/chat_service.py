from core.engine.remote.deepseek import DEFAULT_DEEPSEEK_MODEL


class ChatService:
    """
    General chat service.
    """

    def __init__(self, model_engine):
        self.model_engine = model_engine

    def ask_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        max_new_tokens: int = 512,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        use_thinking_mode: bool = True,
        use_async_client: bool = False,
    ):
        """
        Stream a general chat response.
        Returns a sync generator or async generator depending on client type.
        """
        if use_async_client:
            return self._ask_stream_async(
                prompt, system_prompt, max_new_tokens, model, use_thinking_mode
            )
        else:
            return self._ask_stream_sync(
                prompt, system_prompt, max_new_tokens, model, use_thinking_mode
            )

    async def _ask_stream_async(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int,
        model: str,
        use_thinking_mode: bool,
    ):
        import json

        full_response = ""

        def handle_chunk(chunk):
            nonlocal full_response
            if isinstance(chunk, dict):
                msg_type = chunk.get("type", "content")
                content = chunk.get("delta", "")
                if msg_type == "thinking":
                    return "thinking", content
                if msg_type == "content":
                    full_response += content
                    return "token", content
                return None

            token = str(chunk)
            full_response += token
            return "token", token

        stream = self.model_engine.generate_stream_async(
            prompt=prompt,
            system_prompt=system_prompt or "",
            max_new_tokens=max_new_tokens,
            model=model,
            thinking_enabled=use_thinking_mode,
        )

        async for chunk in stream:
            parsed = handle_chunk(chunk)
            if not parsed:
                continue
            msg_type, content = parsed
            
            if msg_type == "thinking":
                yield (
                    json.dumps(
                        {"type": "thinking", "content": content}, ensure_ascii=False
                    )
                    + "\n"
                )
            else:
                yield (
                    json.dumps(
                        {"type": "token", "content": content}, ensure_ascii=False
                    )
                    + "\n"
                )

        yield (
            json.dumps(
                {"type": "result", "data": {"answer": full_response}},
                ensure_ascii=False,
            )
            + "\n"
        )

    def _ask_stream_sync(
        self,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int,
        model: str,
        use_thinking_mode: bool,
    ):
        import json

        full_response = ""

        def handle_chunk(chunk):
            nonlocal full_response
            if isinstance(chunk, dict):
                msg_type = chunk.get("type", "content")
                content = chunk.get("delta", "")
                if msg_type == "thinking":
                    return "thinking", content
                if msg_type == "content":
                    full_response += content
                    return "token", content
                return None

            token = str(chunk)
            full_response += token
            return "token", token

        stream = self.model_engine.generate_stream(
            prompt=prompt,
            system_prompt=system_prompt or "",
            max_new_tokens=max_new_tokens,
            model=model,
            thinking_enabled=use_thinking_mode,
        )

        for chunk in stream:
            parsed = handle_chunk(chunk)
            if not parsed:
                continue
            msg_type, content = parsed

            if msg_type == "thinking":
                yield (
                    json.dumps(
                        {"type": "thinking", "content": content}, ensure_ascii=False
                    )
                    + "\n"
                )
            else:
                yield (
                    json.dumps(
                        {"type": "token", "content": content}, ensure_ascii=False
                    )
                    + "\n"
                )

        yield (
            json.dumps(
                {"type": "result", "data": {"answer": full_response}},
                ensure_ascii=False,
            )
            + "\n"
        )
