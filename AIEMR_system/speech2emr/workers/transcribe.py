# workers/transcribe.py 
from celery import shared_task
import logging
from app.asr import get_asr_pipeline
from app.settings import settings
from app.audio_io import load_and_preprocess_to_16k_mono
from app.model_registry import get_registry

from emr.service import generate_emr_for_transcription


logger = logging.getLogger(__name__)
_pipe = None

@shared_task
def run_transcription_task(filepath: str, output_path: str, adapter: str | None = None):
    try:
        # Clear GPU memory before starting to avoid dtype conflicts and fragmentation
        import torch
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            # Try to reduce memory fragmentation
            try:
                import os
                os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'
            except:
                pass
            
        pipe = get_registry().get_pipeline(adapter)
        result = pipe(filepath, return_timestamps=True)  # type: ignore
        
        # Handle different result formats
        if isinstance(result, dict):
            transcript = result.get("text", "")
        elif isinstance(result, list) and len(result) > 0:
            transcript = result[0].get("text", "") if isinstance(result[0], dict) else str(result[0])
        else:
            transcript = str(result)
            
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(transcript)
        logger.info(f"Transcription complete: {output_path} (adapter={adapter})")
        
        # Final cleanup before returning
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
    except Exception as e:
        logger.error(f"Transcription task failed: {e}")
        raise


# Note: EMR conversion is now handled in app/main.py run_transcription_simple/run_transcription functions
# This ensures adapter information is properly passed through the conversion pipeline