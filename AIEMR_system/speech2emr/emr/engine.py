# app/emr/engine.py
from typing import Dict
import json
import torch
from guidance import system, user
from guidance import json as gen_json
from guidance.models import Transformers
from transformers import AutoTokenizer, AutoModelForCausalLM
from transformers.utils.quantization_config import BitsAndBytesConfig
from pydantic import BaseModel, Field
from typing import Optional
import logging

# Import GPU monitor
try:
    from app.gpu_monitor import GPUMemoryMonitor
except ImportError:
    # Fallback if not available
    class GPUMemoryMonitor:
        @staticmethod
        def log_gpu_memory_status(context=""):
            pass
        @staticmethod
        def cleanup_gpu_memory(aggressive=False):
            pass

log = logging.getLogger(__name__)

# Keep schema consistent with your prompt fields
class MenstrualHistory(BaseModel):
    name: str
    title: str
    age_menarche: int = Field(ge=8, le=19)
    lmp: Optional[str] = None
    reg: Optional[str] = None
    flow: Optional[str] = None
    dys: Optional[str] = None
    inter_bleed: Optional[str] = None
    consang: Optional[str] = None
    bowel: Optional[str] = None
    cycle: Optional[int] = Field(ge=21, le=46)
    menstruation_len: Optional[int] = Field(ge=2, le=10)
    amen: Optional[str] = None
    amen_type: Optional[str] = None
    med_used: Optional[str] = None
    medicine: Optional[str] = None

class EMREngine:
    def __init__(self, base_model_name: str = "openai/gpt-oss-20b", use_quantization: bool = True, allow_cpu_fallback: bool = True, prefer_full_gpu: bool = False):
        self.base_model_name = base_model_name
        self.model = None
        self.tokenizer = None
        self.llm = None
        self.use_quantization = use_quantization
        self.allow_cpu_fallback = allow_cpu_fallback
        self.prefer_full_gpu = prefer_full_gpu  # Use full GPU when Whisper is cleared
        self.device = None
        
    def _load_model(self):
        """Lazy load the model to avoid keeping it in memory when not needed"""
        if self.model is not None:
            return
            
        log.info(f"Loading EMR model: {self.base_model_name} (quantization={self.use_quantization}, full_gpu={self.prefer_full_gpu})")
        
        # Check initial CUDA availability
        if torch.cuda.is_available():
            log.info(f"CUDA is available. Device count: {torch.cuda.device_count()}")
            log.info(f"Current CUDA device: {torch.cuda.current_device()}")
            
            # Force cleanup before loading (important for Colab)
            import gc
            gc.collect()
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            
        else:
            log.warning("CUDA is not available - will use CPU")
        
        self.tokenizer = AutoTokenizer.from_pretrained(self.base_model_name)
        
        try:
            if self.prefer_full_gpu and torch.cuda.is_available():
                # Priority 1: Full GPU without quantization (after Whisper is cleared)
                log.info("Attempting full GPU loading (no quantization) - Whisper cleared")
                
                # Check available GPU memory first
                total_memory = torch.cuda.get_device_properties(0).total_memory
                allocated_memory = torch.cuda.memory_allocated(0)
                free_memory = total_memory - allocated_memory
                free_gb = free_memory / (1024**3)
                
                log.info(f"GPU Memory Status before EMR loading:")
                log.info(f"  Total: {total_memory / (1024**3):.1f} GB")
                log.info(f"  Allocated: {allocated_memory / (1024**3):.1f} GB") 
                log.info(f"  Available: {free_gb:.1f} GB")
                
                if free_gb > 15:  # Lower threshold for Colab (was 25)
                    # Force all parameters to GPU 0 - no offloading allowed
                    log.info("Sufficient memory detected - forcing full GPU placement")
                    self.model = AutoModelForCausalLM.from_pretrained(
                        self.base_model_name, 
                        device_map={"": "cuda:0"},  # Force everything to GPU 0, no offloading
                        torch_dtype=torch.float16,  # Explicitly use float16, not bfloat16
                        low_cpu_mem_usage=True,
                        max_memory={0: f"{int(free_gb-2)}GB"},  # Reserve 2GB buffer
                        trust_remote_code=True  # Add this for some models that need it
                    )
                    log.info("Model loaded entirely on GPU 0 (no offloading)")
                else:
                    # Less memory available, allow some offloading but try GPU first
                    log.info("Limited memory detected - allowing auto device mapping")
                    self.model = AutoModelForCausalLM.from_pretrained(
                        self.base_model_name, 
                        device_map="auto", 
                        torch_dtype=torch.float16,  # Fix typo: remove quotes from torch.float16
                        low_cpu_mem_usage=True
                    )
                
                self.device = "cuda"
                
                # Validate model dtype
                first_param_dtype = next(self.model.parameters()).dtype
                log.info(f"Model loaded with dtype: {first_param_dtype}")
                if first_param_dtype != torch.float16:
                    log.warning(f"Expected float16 but got {first_param_dtype}, converting...")
                    # Only convert if model is not offloaded
                    if not hasattr(self.model, 'hf_device_map') or all(device == 0 for device in self.model.hf_device_map.values()):
                        self.model = self.model.to(torch.float16)
                
                log.info("Successfully loaded EMR model on full GPU (no quantization, float16)")
                
            elif self.use_quantization and torch.cuda.is_available():
                # Priority 2: GPU with quantization (when GPU memory is limited)
                log.info("Attempting GPU loading with 8-bit quantization")
                quantization_config = BitsAndBytesConfig(
                    load_in_8bit=True,
                    llm_int8_threshold=6.0,
                    llm_int8_has_fp16_weight=False
                )
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.base_model_name, 
                    quantization_config=quantization_config,
                    device_map="auto",
                    torch_dtype=torch.float16,
                    low_cpu_mem_usage=True
                )
                self.device = "cuda"
                
                # For quantized models, ensure guidance compatibility
                log.info("Successfully loaded EMR model on GPU with quantization")
                
            elif torch.cuda.is_available():
                # Priority 3: GPU without quantization (fallback)
                log.info("Attempting GPU loading without quantization")
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.base_model_name, 
                    device_map="auto", 
                    torch_dtype=torch.float16,
                    low_cpu_mem_usage=True
                )
                # Ensure dtype consistency
                self.model = self.model.to(torch.float16)
                self.device = "cuda"
                
                # Validate model dtype
                first_param_dtype = next(self.model.parameters()).dtype
                log.info(f"Model loaded with dtype: {first_param_dtype}")
                
                log.info("Successfully loaded EMR model on GPU (no quantization)")
                
        except Exception as gpu_error:
            log.warning(f"GPU loading failed: {gpu_error}")
            log.warning(f"GPU error type: {type(gpu_error)}")
            log.warning(f"GPU error details: {str(gpu_error)}")
            
            if self.allow_cpu_fallback:
                log.info("Falling back to CPU loading")
                try:
                    # CPU loading with consistent float32 dtype
                    self.model = AutoModelForCausalLM.from_pretrained(
                        self.base_model_name, 
                        device_map="cpu",
                        torch_dtype=torch.float32,  # Use float32 for CPU consistency
                        low_cpu_mem_usage=True
                    )
                    self.device = "cpu"
                    
                    # Ensure all model parameters are in float32 for CPU
                    self.model = self.model.to(torch.float32)
                    log.info("EMR model loaded successfully on CPU with float32")
                    
                except Exception as cpu_error:
                    log.error(f"Both GPU and CPU loading failed. GPU: {gpu_error}, CPU: {cpu_error}")
                    raise cpu_error
            else:
                raise gpu_error
        
        # Fallback to CPU if no GPU available
        if self.model is None:
            log.info("No GPU available, loading on CPU")
            self.model = AutoModelForCausalLM.from_pretrained(
                self.base_model_name, 
                device_map="cpu",
                torch_dtype=torch.float32,  # Use float32 for CPU consistency
                low_cpu_mem_usage=True
            )
            self.model = self.model.to(torch.float32)
            self.device = "cpu"
        
        # Create guidance LLM with explicit dtype handling
        if self.device == "cpu":
            # For CPU, ensure guidance uses float32
            self.llm = Transformers(
                self.model, 
                tokenizer=self.tokenizer, 
                temperature=0.0, 
                use_cache=True,
                torch_dtype=torch.float32
            )
            log.info("Guidance initialized with float32 for CPU")
        else:
            # For GPU, ensure model is actually on CUDA before creating guidance
            if hasattr(self.model, 'device'):
                model_device = str(self.model.device)
                log.info(f"Model device: {model_device}")
            
            # Verify model parameters are on GPU
            param_devices = {name: param.device for name, param in self.model.named_parameters()}
            unique_devices = set(param_devices.values())
            log.info(f"Model parameter devices: {unique_devices}")
            
            # For GPU, explicitly use float16 (not bfloat16)
            self.llm = Transformers(
                self.model, 
                tokenizer=self.tokenizer, 
                temperature=0.0, 
                use_cache=True,
                torch_dtype=torch.float16  # Explicit float16 for guidance
            )
            log.info("Guidance initialized with float16 for GPU")
        
        log.info(f"EMR model loaded successfully on {self.device}")
    
    def _clear_model(self):
        """Clear model from memory to free GPU space"""
        if self.model is not None:
            log.info("Clearing EMR model from memory")
            del self.model
            del self.llm
            self.model = None
            self.llm = None
            
            import gc
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            # Log memory status after clearing
            GPUMemoryMonitor.log_gpu_memory_status("After EMR model cleared")
            log.info("EMR model cleared from GPU memory")

    def convert(self, transcript_text: str, example_text: str, example_json: dict) -> Dict:
        """Convert transcript to EMR JSON with automatic memory management"""
        try:
            # Load model only when needed
            self._load_model()
            
            # Log GPU memory after loading EMR model
            GPUMemoryMonitor.log_gpu_memory_status("After EMR model loaded")
            
            # Ensure llm is loaded
            if self.llm is None:
                raise RuntimeError("Failed to load EMR model")
            
            # Final dtype validation before inference
            if self.model is not None:
                model_dtype = next(self.model.parameters()).dtype
                model_device = next(self.model.parameters()).device
                log.info(f"Starting EMR conversion with model dtype: {model_dtype}, device: {model_device}")
                
                # Verify device consistency
                if self.device == "cuda" and model_device.type == "cpu":
                    log.error("Device mismatch detected! Expected GPU but model is on CPU")
                    raise RuntimeError(f"Model device mismatch: expected cuda but got {model_device}")
                
                # Ensure consistency for guidance operations
                if self.device == "cuda" and model_dtype == torch.bfloat16:
                    log.warning("Model loaded in BFloat16, converting to Float16 for guidance compatibility")
                    self.model = self.model.to(torch.float16)
                    # Recreate guidance with correct dtype
                    self.llm = Transformers(
                        self.model, 
                        tokenizer=self.tokenizer, 
                        temperature=0.0, 
                        use_cache=True,
                        torch_dtype=torch.float16
                    )
            
            with system():
                self.llm += f"""
You are a professional medical doctor.
You need to convert a raw transcript of a medical conversation into JSON ready for an EMR system.
SCHEMA:
name = patient's name
title = patient's title (Mr/Mrs/Ms/Dr/etc)
age_menarche = age at first menstruation (integer 8-19)
lmp = date of last menstrual period (string "YYYY-MM-DD" or null)
amen = whether the amenorrhea exists(boolean true/false or null)
amen_type = type of amenorrhea (string or null)
med_used = whether medication is used (boolean true/false or null)
medicine = medication used (string or null)
cycle = cycle duration in days (integer 21-46 or null)
menstruation_len = length of menstruation in days (integer 2-10 or null)
bowel = whether bowel changes exist (boolean true/false or null)
reg = menstrual regularity (string or null)
flow = menstruation flow (string or null)
dys = dysmenorrhea (string or null) 
inter_bleed = intermenstrual bleeding (string or null)
consang = consanguinity (boolean true/false or null)

EXAMPLE (format reference only):
Raw Transcript:
{example_text}
EMR JSON after conversion:
{example_json}
"""
            with user():
                self.llm += f"""
NEW PATIENT CASE (Raw Transcript):
{transcript_text}

Rules:
- Base every field strictly on the transcript.
- If a field is not present, output the string "Null".
"""

            out = self.llm + gen_json(name="menstrual_history", schema=MenstrualHistory, temperature=0.0)
            result = json.loads(out["menstrual_history"])
            
            # Clear model from memory after conversion to free GPU space
            self._clear_model()
            
            return result
            
        except Exception as e:
            # Make sure to clear model even if conversion fails
            self._clear_model()
            raise e
