import logging, os, threading, uuid
from pathlib import Path
from typing import Dict, Optional
from functools import lru_cache

import torch
import sounddevice as sd
import soundfile as sf

from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq
from transformers.pipelines import pipeline
from transformers.generation.configuration_utils import GenerationConfig
from peft import PeftModel

from sqlmodel import Session
from app import crud, models
from app.database import engine
from app.settings import settings
from .model_registry import get_registry

log = logging.getLogger(__name__)

# ------------------------- LoRA-aware pipeline loader -------------------------
def _device_and_dtype():
    if torch.cuda.is_available():
        return 0, torch.float16
    return "cpu", torch.float32

@lru_cache(maxsize=1)
def get_asr_pipeline():
    device, dtype = _device_and_dtype()

    base_id = settings.STT_MODEL_NAME
    adapter_path = str(settings.STT_ADAPTERS_DIR) if settings.STT_ADAPTERS_DIR and os.path.isdir(settings.STT_ADAPTERS_DIR) else None

    # Prefer processor from adapter folder saved during fine-tuning
    processor_src = adapter_path or base_id
    processor = AutoProcessor.from_pretrained(processor_src)

    # Load base, then attach/merge LoRA
    base = AutoModelForSpeechSeq2Seq.from_pretrained(
        base_id,
        torch_dtype=dtype,
        low_cpu_mem_usage=True
    )
    if adapter_path:
        model = PeftModel.from_pretrained(base, adapter_path)
        if settings.STT_MERGE_LORA:
            model = model.merge_and_unload()
    else:
        model = base

    # Decoding config consistent with FT inference (task/language)
    model.config.forced_decoder_ids = None
    # Try loading a saved generation_config from the processor/adapter folder.
    # If it doesn't exist (common for some saved adapters), fall back to the
    # model's default generation_config to avoid crashing on startup.
    try:
        if os.path.isdir(processor_src):
            gen = GenerationConfig.from_pretrained(processor_src)
        else:
            gen = model.generation_config
    except Exception as e:
        log.warning(
            "Could not load generation_config from %s: %s. Falling back to model.generation_config",
            processor_src,
            e,
        )
        gen = model.generation_config

    # Note: task and language are set in the pipeline's generate_kwargs instead
    model.generation_config = gen

    return pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        device=device
    )

# ------------------------------- Service API ---------------------------------
class ASRService:
    def __init__(self):
        # Load once per process (cached)
        self.registry = get_registry() 
        self.recording_threads = {}
        self.stop_flags = {}
        self.file_paths = {}
        self.patient_ids = {}

    def clear_gpu_memory(self):
        """Clear GPU memory to free space for other models"""
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            log.info("GPU memory cleared")
    
    def unload_whisper_models(self):
        """Completely unload all Whisper models from GPU to free maximum memory"""
        log.info("Unloading all Whisper models from GPU")
        
        # Clear the model registry cache
        if hasattr(self, 'registry') and self.registry:
            if hasattr(self.registry, '_pipelines'):
                for adapter_key, pipeline in self.registry._pipelines.items():
                    try:
                        # Move model to CPU and delete (safe attribute access)
                        if hasattr(pipeline, 'model') and getattr(pipeline, 'model', None) is not None:
                            getattr(pipeline, 'model').cpu()
                            delattr(pipeline, 'model')
                        if hasattr(pipeline, 'feature_extractor'):
                            delattr(pipeline, 'feature_extractor')
                        if hasattr(pipeline, 'tokenizer'):
                            delattr(pipeline, 'tokenizer')
                        log.info(f"Unloaded Whisper pipeline for adapter: {adapter_key}")
                    except Exception as e:
                        log.warning(f"Error unloading pipeline {adapter_key}: {e}")
                
                # Clear the pipeline cache
                self.registry._pipelines.clear()
        
        # Clear the global ASR pipeline cache
        try:
            if hasattr(get_asr_pipeline, 'cache_clear'):
                get_asr_pipeline.cache_clear()  # type: ignore
        except Exception as e:
            log.warning(f"Could not clear ASR pipeline cache: {e}")
            
        # Aggressive memory cleanup
        import gc
        gc.collect()
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            
            # Log GPU memory status
            total_memory = torch.cuda.get_device_properties(0).total_memory
            reserved_memory = torch.cuda.memory_reserved(0)
            allocated_memory = torch.cuda.memory_allocated(0)
            free_memory = total_memory - reserved_memory
            
            log.info(f"GPU Memory after Whisper unload:")
            log.info(f"  Total: {total_memory / 1024**3:.1f} GB")
            log.info(f"  Allocated: {allocated_memory / 1024**3:.1f} GB") 
            log.info(f"  Reserved: {reserved_memory / 1024**3:.1f} GB")
            log.info(f"  Free: {free_memory / 1024**3:.1f} GB")
        
        log.info("Whisper models completely unloaded from GPU")
    
    def reload_whisper_if_needed(self):
        """Reload Whisper models if they were unloaded"""
        if not hasattr(self, 'registry') or not self.registry or not self.registry._pipelines:
            log.info("Reloading Whisper models for new transcription")
            # Force registry recreation
            self.registry = get_registry()
            log.info("Whisper models reloaded successfully")

    # -------- Live recording (demo-only) ----------
    def start_live_recording(self, patient_id: str):
        audio_id = str(uuid.uuid4())
        filename = f"{audio_id}.wav"
        file_path = Path("uploads") / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)

        stop_flag = threading.Event()
        self.stop_flags[audio_id] = stop_flag
        self.file_paths[audio_id] = file_path
        self.patient_ids[audio_id] = patient_id

        th = threading.Thread(
            target=self._record,
            args=(file_path, stop_flag),
            daemon=True,
        )
        self.recording_threads[audio_id] = th
        log.info("Live recording thread started for patient=%s", patient_id)
        th.start()
        return audio_id

    def stop_live_recording(self, audio_id: str):
        if audio_id not in self.stop_flags:
            raise ValueError(f"No active recording found with ID: {audio_id}")
        self.stop_flags[audio_id].set()
        self.recording_threads[audio_id].join()

        file_path = self.file_paths[audio_id]
        patient_name = self.patient_ids[audio_id]
        log.info("Recording stopped. File saved at %s", file_path)

        with Session(engine) as session:
            # Mirror main.py behavior: create/get by "name"
            patient = crud.get_or_create_patient(session, patient_name)
            if patient.id is not None:
                recording = crud.create_recording(session, patient.id)
                audio = models.Audio(
                    filepath=str(file_path), 
                    recording_id=recording.id,
                    language=None,
                    duration=None
                )
                session.add(audio)
                session.commit()

        output_path = f"transcripts/{audio_id}.txt"
        if settings.USE_CELERY:
            # Lazy import to avoid hard dependency on a workers package
            try:
                from workers.transcribe import run_transcription_task  # adjust to your actual module path
                run_transcription_task.delay(filepath=str(file_path), output_path=output_path)  # type: ignore
            except ImportError:
                try:
                    from workers.transcribe import run_transcription_task  # fallback if you have a workers/ package
                    run_transcription_task.delay(filepath=str(file_path), output_path=output_path)  # type: ignore
                except ImportError:
                    log.warning("Celery task not available, falling back to synchronous transcription")
                    text = self.transcribe(file_path)
                    Path(output_path).write_text(text, encoding="utf-8")
        else:
            text = self.transcribe(file_path)
            Path(output_path).write_text(text, encoding="utf-8")

        return {"status": "stopped", "audio_id": audio_id, "path": str(file_path)}

    def _record(self, file_path: Path, stop_flag: threading.Event):
        samplerate, channels, subtype = 16000, 1, "PCM_16"
        try:
            with sf.SoundFile(file_path, mode="x", samplerate=samplerate, channels=channels, subtype=subtype) as f:
                with sd.InputStream(samplerate=samplerate, channels=channels):
                    log.info("Recording started.")
                    while not stop_flag.is_set():
                        data = sd.rec(frames=1024, samplerate=samplerate, channels=channels, dtype="int16")
                        sd.wait()
                        f.write(data)
        except Exception as e:
            log.error("Error during recording: %s", e)

    # -------- Batch transcription ----------
    def transcribe(self, wav_path: Path, adapter_key: str | None = None) -> str:
        try:
            # Reload Whisper models if they were unloaded
            self.reload_whisper_if_needed()
            
            pipe = self.registry.get_pipeline(adapter_key)
            # Use clean parameters to minimize warnings
            result = pipe(str(wav_path))  # type: ignore

            # Release the GPU memory after the transcription is done
            self.clear_gpu_memory()

            # Handle different result formats
            if isinstance(result, dict):
                return result.get("text", "")
            elif isinstance(result, list) and len(result) > 0:
                return result[0].get("text", "") if isinstance(result[0], dict) else str(result[0])
            else:
                return str(result)
            
        except Exception as e:
            log.error(f"Transcription failed for {wav_path} [{adapter_key}]: {e}")
            return ""