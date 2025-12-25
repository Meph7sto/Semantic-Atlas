import os
from typing import List, Optional

import joblib
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


class RequirementClassificationEngine:
    """Lightweight encoder-based classifier for requirement categories."""

    def __init__(
        self,
        model_path: str,
        label_encoder_path: Optional[str] = None,
        batch_size: int = 32,
        max_seq_len: int = 256,
    ) -> None:
        self.model_path = model_path
        self.label_encoder_path = label_encoder_path
        self.batch_size = batch_size
        self.max_seq_len = max_seq_len
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model: Optional[AutoModelForSequenceClassification] = None
        self.tokenizer: Optional[AutoTokenizer] = None
        self.label_encoder = None
        self.id2label = {}

    @property
    def is_ready(self) -> bool:
        return self.model is not None and self.tokenizer is not None

    def load(self) -> None:
        """Load tokenizer, model, and label encoder if available."""
        print(f"Loading classification model from {self.model_path}...")
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Classification model path not found: {self.model_path}")

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path, use_fast=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_path)
        self.model.to(self.device)
        self.model.eval()

        # Try load label encoder for human-readable labels
        if self.label_encoder_path and os.path.exists(self.label_encoder_path):
            try:
                self.label_encoder = joblib.load(self.label_encoder_path)
                self.id2label = {idx: label for idx, label in enumerate(self.label_encoder.classes_)}
            except Exception as exc:
                print(f"Warning: failed to load label encoder: {exc}")
                self.id2label = {}
        elif hasattr(self.model.config, "id2label"):
            self.id2label = {int(idx): label for idx, label in self.model.config.id2label.items()}
        print("Classification model loaded successfully.")

    def _ensure_ready(self) -> None:
        if not self.is_ready:
            raise RuntimeError("Classification model is not loaded. Call load() before inference.")

    def _map_label(self, label_id: int) -> str:
        if label_id in self.id2label:
            return str(self.id2label[label_id])
        return str(label_id)

    def predict(
        self,
        texts: List[str],
        batch_size: Optional[int] = None,
        max_length: Optional[int] = None,
    ) -> List[str]:
        """Classify a batch of requirements."""
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
