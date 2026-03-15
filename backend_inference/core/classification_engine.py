import json
import os
import re
from typing import List, Optional

import joblib
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from .engine.remote import ChutesClient, DeepSeekClient

DEFAULT_CLASSIFICATION_LABELS = [
    "功能性需求",
    "性能需求",
    "安全需求",
    "可靠性需求",
    "可用性需求",
    "兼容性需求",
    "可维护性需求",
    "其他",
]

SYSTEM_PROMPT_CLASSIFICATION = """你是资深需求工程专家，负责将需求文本归类到给定标签中。
必须严格输出有效 JSON，且 label 只能取自提供的标签列表。
不要输出任何多余解释、Markdown 或前后缀。"""


def _extract_first_json_object(text: str) -> Optional[dict]:
    if not text:
        return None
    s = text.strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    s = s.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


class RequirementClassificationEngine:
    """Lightweight encoder-based classifier for requirement categories."""

    def __init__(
        self,
        model_path: str,
        label_encoder_path: Optional[str] = None,
        batch_size: int = 32,
        max_seq_len: int = 256,
        provider: str = "local",
        chutes_api_url: Optional[str] = None,
        chutes_api_token: Optional[str] = None,
        deepseek_api_url: Optional[str] = None,
        deepseek_api_key: Optional[str] = None,
        deepseek_model: Optional[str] = None,
        labels: Optional[List[str]] = None,
        other_label: str = "其他",
    ) -> None:
        self.model_path = model_path
        self.label_encoder_path = label_encoder_path
        self.batch_size = batch_size
        self.max_seq_len = max_seq_len
        self.provider = (provider or "local").lower()
        self.chutes_api_url = chutes_api_url or ""
        self.chutes_api_token = chutes_api_token
        self.deepseek_api_url = deepseek_api_url or ""
        self.deepseek_api_key = deepseek_api_key
        self.deepseek_model = deepseek_model or "deepseek-chat"
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model: Optional[AutoModelForSequenceClassification] = None
        self.tokenizer: Optional[AutoTokenizer] = None
        self.label_encoder = None
        self.id2label = {}
        self._remote_client = None
        self._user_labels = self._normalize_label_list(labels)
        self.other_label = other_label or "其他"
        self.labels: List[str] = []

    @property
    def is_ready(self) -> bool:
        if self.provider != "local":
            return True
        return self.model is not None and self.tokenizer is not None

    def load(self) -> None:
        """Load tokenizer, model, and label encoder if available."""
        if self.provider != "local":
            print(f"Using remote provider '{self.provider}', skip local classification model loading.")
            self._load_label_encoder()
            self._resolve_label_list()
            self.model = "api"
            self.tokenizer = None
            return

        print(f"Loading classification model from {self.model_path}...")
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Classification model path not found: {self.model_path}")

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, use_fast=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_path)
        self.model.to(self.device)
        self.model.eval()

        self._load_label_encoder()
        if not self.id2label and hasattr(self.model.config, "id2label"):
            self.id2label = {int(idx): label for idx, label in self.model.config.id2label.items()}
        self._resolve_label_list()
        print("Classification model loaded successfully.")

    def _ensure_ready(self) -> None:
        if self.provider != "local":
            if not self.labels:
                self._resolve_label_list()
            return
        if not self.is_ready:
            raise RuntimeError("Classification model is not loaded. Call load() before inference.")

    def _map_label(self, label_id: int) -> str:
        if label_id in self.id2label:
            return str(self.id2label[label_id])
        return str(label_id)

    def _normalize_label_list(self, labels: Optional[List[str]]) -> List[str]:
        if not labels:
            return []
        raw_list: List[str] = []
        if isinstance(labels, str):
            try:
                parsed = json.loads(labels)
                if isinstance(parsed, list):
                    raw_list = [str(item) for item in parsed]
                else:
                    raw_list = [s for s in labels.split(",")]
            except json.JSONDecodeError:
                raw_list = [s for s in labels.split(",")]
        else:
            raw_list = [str(item) for item in labels]

        seen = set()
        normalized: List[str] = []
        for item in raw_list:
            cleaned = str(item).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized

    def _load_label_encoder(self) -> None:
        if self.label_encoder_path and os.path.exists(self.label_encoder_path):
            try:
                self.label_encoder = joblib.load(self.label_encoder_path)
                self.id2label = {idx: label for idx, label in enumerate(self.label_encoder.classes_)}
            except Exception as exc:
                print(f"Warning: failed to load label encoder: {exc}")
                self.id2label = {}

    def _resolve_label_list(self) -> None:
        if self._user_labels:
            labels = list(self._user_labels)
        elif self.id2label:
            labels = [str(self.id2label[idx]) for idx in sorted(self.id2label)]
        else:
            labels = list(DEFAULT_CLASSIFICATION_LABELS)

        if self.other_label and self.other_label not in labels:
            labels.append(self.other_label)

        seen = set()
        deduped: List[str] = []
        for label in labels:
            cleaned = str(label).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)
        self.labels = deduped

    def _get_remote_client(self):
        if self.provider == "chutes":
            if not isinstance(self._remote_client, ChutesClient):
                self._remote_client = ChutesClient(self.chutes_api_url, self.chutes_api_token)
            return self._remote_client
        if self.provider == "deepseek":
            if not isinstance(self._remote_client, DeepSeekClient):
                self._remote_client = DeepSeekClient(
                    self.deepseek_api_url,
                    self.deepseek_api_key,
                    model=self.deepseek_model,
                )
            return self._remote_client
        raise RuntimeError(f"Unsupported classification provider: {self.provider}")

    def _build_prompt(self, requirement: str, labels: List[str]) -> str:
        label_text = "，".join(labels)
        return (
            "请将以下需求文本归类到给定标签之一。\n"
            f"标签列表：{label_text}\n"
            f"需求文本：{requirement}\n"
            "仅输出 JSON，例如：{\"label\":\"性能需求\",\"confidence\":0.78}\n"
            f"若无法判断，请输出 {self.other_label}。"
        )

    def _match_label_in_text(self, text: str, labels: List[str]) -> Optional[str]:
        if not text:
            return None
        for label in labels:
            if label and label in text:
                return label
        for label in labels:
            if label.endswith("需求") and label[:-2] and label[:-2] in text:
                return label
            if not label.endswith("需求") and f"{label}需求" in text:
                return label
        return None

    def _parse_remote_label(self, raw: str, labels: List[str]) -> str:
        parsed = _extract_first_json_object(raw)
        label = None
        if parsed:
            for key in ("label", "predicted_label", "category", "class"):
                if key in parsed:
                    label = parsed.get(key)
                    break

        if label is not None:
            label = str(label).strip().strip('"').strip("'")
            if label in labels:
                return label
            match = self._match_label_in_text(label, labels)
            if match:
                return match

        match = self._match_label_in_text(raw, labels)
        return match or (self.other_label if self.other_label else labels[-1])

    def _predict_remote(
        self,
        texts: List[str],
        max_length: Optional[int] = None,
    ) -> List[str]:
        self._ensure_ready()
        labels = self.labels or list(DEFAULT_CLASSIFICATION_LABELS)
        if self.other_label and self.other_label not in labels:
            labels.append(self.other_label)
        client = self._get_remote_client()
        predictions: List[str] = []
        for text in texts:
            item = "" if text is None else str(text).strip()
            if max_length:
                item = item[:max_length]
            if not item:
                predictions.append(self.other_label)
                continue
            prompt = self._build_prompt(item, labels)
            raw = client.generate(prompt=prompt, system_prompt=SYSTEM_PROMPT_CLASSIFICATION, max_new_tokens=96)
            predictions.append(self._parse_remote_label(raw, labels))
        return predictions

    def predict(
        self,
        texts: List[str],
        batch_size: Optional[int] = None,
        max_length: Optional[int] = None,
    ) -> List[str]:
        """Classify a batch of requirements."""
        if self.provider != "local":
            return self._predict_remote(texts, max_length=max_length)

        self._ensure_ready()
        if not texts:
            return []

        bs = batch_size or self.batch_size
        max_len = max_length or self.max_seq_len
        predictions: List[str] = []

        with torch.no_grad():
            for start in range(0, len(texts), bs):
                batch_texts = texts[start : start + bs]
                encodings = self.tokenizer(
                    batch_texts,
                    padding=True,
                    truncation=True,
                    max_length=max_len,
                    return_tensors="pt",
                )
                encodings = {k: v.to(self.device) for k, v in encodings.items()}
                logits = self.model(**encodings).logits
                pred_ids = torch.argmax(logits, dim=1).cpu().tolist()
                predictions.extend([self._map_label(pid) for pid in pred_ids])
        return predictions
