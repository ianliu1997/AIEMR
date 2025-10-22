# emr_tasks.py
from enum import StrEnum
from dataclasses import dataclass
from typing import Callable, Optional, Type
from pydantic import BaseModel
import logging

log = logging.getLogger(__name__)

# ---- Your Pydantic schemas (import if defined elsewhere) ----
from emr.EMRconversion import MenstrualHistory, MedicalHistory

class AdapterKey(StrEnum):
    MENSTRUAL = "model_outputs_seg_MenstrualHistory"
    MEDICAL = "model_outputs_seg_MedicalHistory"

@dataclass(frozen=True)
class EMRTaskConfig:
    # Basic EMR contract
    schema_name: str                   # e.g., "medical_his"
    schema: Type[BaseModel]            # Pydantic schema class
    title: str                         # Human title for section
    null_token: str                    # e.g., "None" vs "Null"

    # LLM configuration for this task
    model_name: str                    # HF model id or endpoint alias
    temperature: float
    # top_p: float                      # Uncomment if using nucleus sampling
    # max_new_tokens: int  limitation of guidance stop parameter
    stop: Optional[list[str]] = None

    # Prompt templates (simple strings; you can make them Jinja if preferred)
    system_template: str = (
        "You are a professional medical doctor.\n"
        "Convert a raw medical conversation into JSON suitable for an EMR system.\n"
        "Do not invent information; use only what appears in the transcript."
    )
    user_template: str = (
        "Extract the relevant clinical information and convert it to JSON for the EMR.\n"
        "If a field is missing in the transcript, use '{null_token}'.\n"
        "Do not include any information that is not present in the transcript.\n\n"
        "RAW TRANSCRIPT:\n{transcript}"
    )

TASKS: dict[str, EMRTaskConfig] = {
    AdapterKey.MEDICAL: EMRTaskConfig(
        schema_name="medical_his",
        schema=MedicalHistory,
        title="Medical History",
        null_token="None",
        model_name="openai/gpt-oss-20b",
        temperature=0.0,
        # top_p=1.0,
        # max_new_tokens=2048,
        stop=None,
    ),
    AdapterKey.MENSTRUAL: EMRTaskConfig(
        schema_name="menstrual_his",
        schema=MenstrualHistory,
        title="Menstrual History",
        null_token="Null",
        model_name="openai/gpt-oss-20b",
        temperature=0.0,
        # top_p=1.0,
        # max_new_tokens=2048,
        stop=None,
    ),
}

def get_task_for_adapter(adapter_key: str) -> EMRTaskConfig:
    """
    Get EMR task configuration for a given adapter key.
    Handles variations in adapter key format (with or without 'model_outputs_seg_' prefix).
    """
    # Normalize adapter key to match enum format
    if adapter_key and not adapter_key.startswith("model_outputs_seg_"):
        adapter_key = f"model_outputs_seg_{adapter_key}"
    
    try:
        return TASKS[AdapterKey(adapter_key)]
    except (ValueError, KeyError):
        # Default/fallback to medical history
        log.warning(f"Unknown adapter key '{adapter_key}', falling back to Medical History")
        return TASKS[AdapterKey.MEDICAL]
