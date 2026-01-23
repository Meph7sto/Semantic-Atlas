import json
import os
import re
from typing import Dict, List, Optional, Tuple

from .constants import RELATION_TYPES
from .models import Span
from .prompts import SYSTEM_PROMPT_LINK, build_window_prompt


class LLMClient:
    def __init__(self, mock_mode: bool = False):
        self.mock_mode = mock_mode or os.environ.get(
            "MOCK_LLM_CONTEXT_BUILDING", ""
        ).lower() in (
            "1",
            "true",
        )
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from backend_inference.core.model_container import model_engine

            self._engine = model_engine
        return self._engine

    def _collect_stream_text(self, stream) -> str:
        chunks = []
        for event in stream:
            if isinstance(event, dict):
                if event.get("type") == "thinking":
                    continue
                delta = event.get("delta") or event.get("content")
                if delta:
                    chunks.append(str(delta))
            elif isinstance(event, (bytes, bytearray)):
                chunks.append(event.decode("utf-8", errors="ignore"))
            elif isinstance(event, str):
                chunks.append(event)
        return "".join(chunks).strip()

    def _generate_text(self, engine, prompt: str, model_name: Optional[str]) -> str:
        if model_name:
            stream = engine.generate_stream(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT_LINK,
                max_new_tokens=1500,
                model=model_name,
            )
            text = self._collect_stream_text(stream)
            if text:
                return text
        return engine.generate(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT_LINK,
            max_new_tokens=1500,
        )

    def generate_links(
        self,
        spans: List[Span],
        ref_map: Dict[str, str],
        model_name: Optional[str] = None,
    ) -> Tuple[List[Dict], List[str]]:
        if self.mock_mode:
            return self._mock_generate(spans, ref_map)

        prompt = build_window_prompt(spans, ref_map)
        engine = self._get_engine()

        try:
            response = self._generate_text(engine, prompt, model_name)
            return self._parse_llm_response(response)
        except Exception as exc:
            print(f"[LLMClient] Error calling LLM: {exc}")
            return [], []

    def _mock_generate(
        self, spans: List[Span], ref_map: Dict[str, str]
    ) -> Tuple[List[Dict], List[str]]:
        links = []
        refs = list(ref_map.values())

        for i in range(len(refs) - 1):
            links.append(
                {
                    "source": refs[i],
                    "target": refs[i + 1],
                    "type": "continuation",
                    "strength": 0.75,
                    "note": "mock continuation",
                }
            )

        return links, []

    def _parse_llm_response(self, response: str) -> Tuple[List[Dict], List[str]]:
        links: List[Dict] = []
        noise: List[str] = []

        response = response.strip()

        if response.startswith("```"):
            lines = response.split("\n")
            start_idx = 0
            end_idx = len(lines)
            for i, line in enumerate(lines):
                if line.strip().startswith("```") and i == 0:
                    start_idx = 1
                elif line.strip() == "```":
                    end_idx = i
                    break
            response = "\n".join(lines[start_idx:end_idx])

        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", response)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    print(f"[LLMClient] Failed to parse JSON: {response[:200]}")
                    return [], []
            else:
                print(f"[LLMClient] No JSON found in response: {response[:200]}")
                return [], []

        raw_links = data.get("links", [])
        if isinstance(raw_links, list):
            for item in raw_links:
                if isinstance(item, dict):
                    link = {
                        "source": str(item.get("source", "")),
                        "target": str(item.get("target", "")),
                        "type": str(item.get("type", "")),
                        "strength": float(item.get("strength", 0)),
                        "note": str(item.get("note", "")),
                    }
                    if link["type"] in RELATION_TYPES:
                        links.append(link)

        raw_noise = data.get("noise", [])
        if isinstance(raw_noise, list):
            noise = [str(n) for n in raw_noise if isinstance(n, (str, int))]

        return links, noise
