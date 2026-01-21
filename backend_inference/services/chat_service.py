class ChatService:
    """
    General chat service.
    """

    def __init__(self, model_engine):
        self.model_engine = model_engine

    def ask_stream(self, prompt: str, system_prompt: str = "", max_new_tokens: int = 512, use_thinking_mode: bool = False):
        """
        Stream a general chat response.
        Yields:
            str: NDJSON lines containing tokens and final answer
        """
        import json

        # Determine model
        model_name = "deepseek-reasoner" if use_thinking_mode else None

        stream = self.model_engine.generate_stream(
            prompt=prompt,
            system_prompt=system_prompt or "",
            max_new_tokens=max_new_tokens,
            model=model_name
        )

        full_response = ""
        for chunk in stream:
            # Handle structured chunks (new engine) or string chunks (legacy/fallback)
            if isinstance(chunk, dict):
                msg_type = chunk.get("type", "content")
                content = chunk.get("delta", "")
                
                if msg_type == "thinking":
                    yield json.dumps({"type": "thinking", "content": content}, ensure_ascii=False) + "\n"
                elif msg_type == "content":
                    full_response += content
                    yield json.dumps({"type": "token", "content": content}, ensure_ascii=False) + "\n"
            else:
                token = str(chunk)
                full_response += token
                yield json.dumps({"type": "token", "content": token}, ensure_ascii=False) + "\n"

        yield json.dumps({"type": "result", "data": {"answer": full_response}}, ensure_ascii=False) + "\n"
