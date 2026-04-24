from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


@dataclass
class SentimentConfig:
    model_path: str
    max_chunk_tokens: int = 512
    device: str = "auto"


class SentimentAnalyzer:
    """Run sequence-classification sentiment on long text via chunk aggregation."""

    def __init__(self, config: SentimentConfig):
        self.config = config
        self.device = self._resolve_device(config.device)
        self.tokenizer = AutoTokenizer.from_pretrained(config.model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(config.model_path)
        self.model.to(self.device)
        self.model.eval()

        self.label_to_index = self._build_label_map(self.model.config.id2label)

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda" and not torch.cuda.is_available():
            return "cpu"
        return device

    @staticmethod
    def _build_label_map(id2label: Dict[int, str]) -> Dict[str, int]:
        normalized = {int(k): str(v).lower() for k, v in id2label.items()}
        out: Dict[str, int] = {}
        for idx, label in normalized.items():
            if "pos" in label:
                out["positive"] = idx
            elif "neg" in label:
                out["negative"] = idx
            elif "neu" in label:
                out["neutral"] = idx

        if {"positive", "neutral", "negative"} <= set(out.keys()):
            return out

        # Common fallback ordering in many 3-label checkpoints.
        if len(normalized) == 3:
            return {"negative": 0, "neutral": 1, "positive": 2}

        raise ValueError(
            "Could not infer sentiment labels from model config. "
            f"id2label={id2label}"
        )

    def _chunk_text(self, text: str) -> List[List[int]]:
        token_ids = self.tokenizer.encode(text, add_special_tokens=False)
        if not token_ids:
            return []

        chunk_size = max(8, self.config.max_chunk_tokens - 2)
        return [token_ids[i : i + chunk_size] for i in range(0, len(token_ids), chunk_size)]

    def _predict_chunk_probs(self, chunk_token_ids: List[int]) -> Dict[str, float]:
        encoded = self.tokenizer.prepare_for_model(
            chunk_token_ids,
            add_special_tokens=True,
            truncation=True,
            max_length=self.config.max_chunk_tokens,
            return_tensors="pt",
        )
        encoded = {k: v.to(self.device) for k, v in encoded.items()}
        with torch.no_grad():
            logits = self.model(**encoded).logits
            probs = torch.softmax(logits, dim=-1).squeeze(0).detach().cpu()

        return {
            "positive": float(probs[self.label_to_index["positive"]].item()),
            "neutral": float(probs[self.label_to_index["neutral"]].item()),
            "negative": float(probs[self.label_to_index["negative"]].item()),
            "token_count": int(encoded["attention_mask"].sum().item()),
        }

    def analyze(self, text: str) -> Dict[str, object]:
        cleaned = (text or "").strip()
        if not cleaned:
            return {
                "label": "neutral",
                "score": 0.0,
                "probabilities": {"positive": 0.0, "neutral": 1.0, "negative": 0.0},
                "model_name": self.config.model_path,
                "num_chunks": 0,
            }

        chunks = self._chunk_text(cleaned)
        if not chunks:
            return {
                "label": "neutral",
                "score": 0.0,
                "probabilities": {"positive": 0.0, "neutral": 1.0, "negative": 0.0},
                "model_name": self.config.model_path,
                "num_chunks": 0,
            }

        weighted = {"positive": 0.0, "neutral": 0.0, "negative": 0.0}
        total_weight = 0

        for chunk in chunks:
            p = self._predict_chunk_probs(chunk)
            w = p["token_count"]
            total_weight += w
            weighted["positive"] += p["positive"] * w
            weighted["neutral"] += p["neutral"] * w
            weighted["negative"] += p["negative"] * w

        if total_weight == 0:
            probs = {"positive": 0.0, "neutral": 1.0, "negative": 0.0}
        else:
            probs = {k: v / total_weight for k, v in weighted.items()}

        score = max(-1.0, min(1.0, probs["positive"] - probs["negative"]))
        label = max(probs, key=probs.get)

        return {
            "label": label,
            "score": float(score),
            "probabilities": probs,
            "model_name": self.config.model_path,
            "num_chunks": len(chunks),
        }


def build_default_model_path() -> str:
    return str(Path(__file__).resolve().parent / "models" / "BERT")
