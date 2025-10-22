from __future__ import annotations
import threading
from pathlib import Path
from typing import Dict, Optional

import torch
from torch import cuda
from transformers import (
    AutoProcessor,
    AutoModelForSpeechSeq2Seq,
)
from transformers.pipelines import pipeline as hf_pipeline
from peft import PeftModel

from .settings import settings

class ModelRegistry:
    """
    Caches one ASR pipeline per adapter key.
    Adapter key examples:
      - None or "base" -> raw BASE_MODEL_NAME
      - "seg_MedicalHistory" -> adapters/seg_MedicalHistory/...
      - "seg_MenstrualHistory" -> adapters/seg_MenstrualHistory/...
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self):
        self._pipelines: Dict[str, object] = {}
        self._device = 0 if cuda.is_available() else -1
        self._base_model_name = settings.STT_MODEL_NAME
        self._adapters_dir = Path(settings.STT_ADAPTERS_DIR)
        self._adapters_dir.mkdir(exist_ok=True)

        # Create a plain "base" pipeline lazily on demand.
        # Adapters will be loaded lazily too.

    def list_adapters(self) -> Dict[str, str]:
        """Return {adapter_key: absolute_path} including special 'base'."""
        out = {"base": "<no adapter>"}
        if self._adapters_dir.exists():
            for p in sorted(self._adapters_dir.iterdir()):
                if p.is_dir() and (p / "adapter_config.json").exists():
                    out[p.name] = str(p.resolve())
        return out

    def _build_base(self):
        processor = AutoProcessor.from_pretrained(self._base_model_name)
        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            self._base_model_name,
            torch_dtype=torch.float16 if cuda.is_available() else torch.float32,
            low_cpu_mem_usage=True,
        )
        return processor, model

    def _build_with_adapter(self, adapter_key: str):
        adapter_dir = self._adapters_dir / adapter_key
        if not (adapter_dir / "adapter_config.json").exists():
            raise FileNotFoundError(f"Adapter '{adapter_key}' not found in {adapter_dir}")

        # Prefer processor saved with the adapter; fall back to base
        try:
            processor = AutoProcessor.from_pretrained(str(adapter_dir))
        except Exception:
            processor = AutoProcessor.from_pretrained(self._base_model_name)

        base = AutoModelForSpeechSeq2Seq.from_pretrained(
            self._base_model_name,
            torch_dtype=torch.float16 if cuda.is_available() else torch.float32,
            low_cpu_mem_usage=True,
        )
        model = PeftModel.from_pretrained(base, str(adapter_dir))
        # Do NOT merge_and_unload() if you plan to keep swapping; we keep it as PEFT.
        return processor, model

    def _make_pipeline(self, adapter_key: Optional[str]):
        key = adapter_key or "base"
        if key in self._pipelines:
            return self._pipelines[key]

        if key == "base":
            processor, model = self._build_base()
        else:
            processor, model = self._build_with_adapter(key)

        pipe = hf_pipeline(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            device=self._device,
            # Remove chunk_length_s to avoid experimental chunking warnings
            # Let Whisper use its native chunking mechanism
            return_timestamps=True,
            generate_kwargs={
                "task": "transcribe",
                "language": "en",
                "condition_on_prev_tokens": True,
            },
        )
        self._pipelines[key] = pipe
        return pipe

    # --- public API ---
    def get_pipeline(self, adapter_key: Optional[str]):
        return self._make_pipeline(adapter_key)

# singleton accessor
def get_registry() -> ModelRegistry:
    return ModelRegistry()
