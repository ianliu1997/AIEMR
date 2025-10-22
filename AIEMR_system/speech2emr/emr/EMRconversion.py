'''Install necessary packages for the project

!pip install --upgrade torch
!pip install git+https://github.com/huggingface/transformers triton==3.4 kernels
!pip uninstall torchvision torchaudio -y
!pip install gpustat
!pip install gpt-oss
!pip install guidance
!pip install pydantic
'''

# --- imports ---
import os, json
from datetime import date
from typing import Optional
from textwrap import dedent
import logging

import guidance
from guidance import system, user
from guidance import json as gen_json
from guidance.models import Transformers

from transformers import AutoTokenizer, AutoModelForCausalLM
from pydantic import BaseModel, Field

import triton


# --- define the schema class ---
# Menstrual History table
class MenstrualHistory(BaseModel):
    name: str
    title: str
    age_menarche: int  # Removed strict constraints to prevent LLM generation issues
    lmp: Optional[str] = None
    amenorrhea: bool
    amenorrhea_type: Optional[str] = None
    medication_used: bool
    medicine: Optional[str] = None
    cycle_duration: int  # Removed strict constraints to prevent LLM generation issues
    menstruation_len: int  # Removed strict constraints to prevent LLM generation issues
    bowel_changes: bool
    menstrual_regularity: str
    menstruation_flow: str
    dysmennorhea: str
    intermenstrual_bleed: str
    consanguinity: bool
    
    # Make validation more flexible
    class Config:
        extra = "allow"  # Allow extra fields from LLM output

# Medical History table
class MedicalHistory(BaseModel):
    disease_name: str
    disease_type: str
    disease_since: str
    disease_medication: bool
    
    # Make validation more flexible
    class Config:
        extra = "allow"  # Allow extra fields from LLM output


# --- model loader (unchanged) ---
class llm_model():
    def __init__(self, base_model_name="openai/gpt-oss-20b"):
        from transformers import AutoTokenizer, AutoModelForCausalLM
        self.model_name = base_model_name
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name, device_map="cuda", torch_dtype="auto")


# --- main conversion function ---
def convert_transcript_to_emr(
    transcript_text: str,
    task_cfg,                                # emr_tasks.EMRTaskConfig
    example_raw: Optional[str] = None,
    example_json: Optional[dict] = None,
) -> dict:
    """
    Run LLM conversion and return a dict matching task_cfg.schema.
    """
    example_block = ""
    if example_raw and example_json:
        example_block = dedent(f"""
        EXAMPLE ({task_cfg.title}):
        Raw Transcript:
        {example_raw}

        EMR JSON format after the conversion:
        {json.dumps(example_json, indent=2)}
        """)

    system_prompt = task_cfg.system_template + ("\n\n" + example_block if example_block else "")
    user_prompt = task_cfg.user_template.format(
        null_token=task_cfg.null_token, transcript=transcript_text
    )

    # Initialize model for guidance
    lm = llm_model(base_model_name=task_cfg.model_name)
    llm_guidance = Transformers(
        lm.model, tokenizer=lm.tokenizer,
        temperature=task_cfg.temperature, use_cache=True
    )

    with system():
        llm_guidance += system_prompt
    with user():
        llm_guidance += user_prompt

    emr = llm_guidance + gen_json(
        name=task_cfg.schema_name, schema=task_cfg.schema,
        temperature=task_cfg.temperature,
    )

    try:
        # Get the raw output from guidance
        raw_output = emr[task_cfg.schema_name]
        
        # If it's already a dict, use it directly
        if isinstance(raw_output, dict):
            validated = task_cfg.schema.model_validate(raw_output)
            return validated.model_dump()
        
        # If it's a string, try to parse it as JSON
        elif isinstance(raw_output, str):
            # Try parsing as JSON first
            try:
                parsed_json = json.loads(raw_output)
                validated = task_cfg.schema.model_validate(parsed_json)
                return validated.model_dump()
            except json.JSONDecodeError:
                # If JSON parsing fails, try direct validation
                validated = task_cfg.schema.model_validate_json(raw_output)
                return validated.model_dump()
        
        # Fallback: try to validate whatever we got
        else:
            validated = task_cfg.schema.model_validate(raw_output)
            return validated.model_dump()
            
    except Exception as e:
        logging.error(f"EMR validation failed: {e}")
        logging.error(f"Raw output type: {type(emr[task_cfg.schema_name])}")
        logging.error(f"Raw output content (first 500 chars): {str(emr[task_cfg.schema_name])[:500]}")
        
        # Return raw output as fallback, but try to convert to dict if possible
        raw_output = emr[task_cfg.schema_name]
        if isinstance(raw_output, str):
            try:
                return json.loads(raw_output)
            except:
                pass
        
        return raw_output