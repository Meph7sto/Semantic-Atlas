class ChatService:
    """
    General chat service.
    """

    def __init__(self, model_engine):
        self.model_engine = model_engine

    def ask_stream(self, prompt: str, system_prompt: str = "", max_new_tokens: int = 512):
        """
        Stream a general chat response.
        Yields:
            str: NDJSON lines containing tokens and final answer
        """
        import json

        stream = self.model_engine.generate_stream(
            prompt=prompt,
            system_prompt=system_prompt or "",
            max_new_tokens=max_new_tokens,
        )

        full_response = ""
        for token in stream:
            full_response += token
            yield json.dumps({"type": "token", "content": token}, ensure_ascii=False) + "\n"

        yield json.dumps({"type": "result", "data": {"answer": full_response}}, ensure_ascii=False) + "\n"
