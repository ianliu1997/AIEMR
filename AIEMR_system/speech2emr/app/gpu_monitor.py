# app/gpu_monitor.py
import torch
import gc
import logging
from typing import Dict, Optional

log = logging.getLogger(__name__)

class GPUMemoryMonitor:
    """Utility class for monitoring and managing GPU memory usage"""
    
    @staticmethod
    def get_gpu_memory_info() -> Optional[Dict[str, float]]:
        """Get current GPU memory information in GB"""
        if not torch.cuda.is_available():
            return None
            
        try:
            total_memory = torch.cuda.get_device_properties(0).total_memory
            reserved_memory = torch.cuda.memory_reserved(0)
            allocated_memory = torch.cuda.memory_allocated(0)
            free_memory = total_memory - reserved_memory
            
            return {
                "total_gb": total_memory / 1024**3,
                "allocated_gb": allocated_memory / 1024**3,
                "reserved_gb": reserved_memory / 1024**3,
                "free_gb": free_memory / 1024**3,
                "utilization_percent": (reserved_memory / total_memory) * 100
            }
        except Exception as e:
            log.warning(f"Failed to get GPU memory info: {e}")
            return None
    
    @staticmethod
    def log_gpu_memory_status(context: str = ""):
        """Log current GPU memory status with context"""
        memory_info = GPUMemoryMonitor.get_gpu_memory_info()
        if memory_info:
            context_str = f" ({context})" if context else ""
            log.info(f"GPU Memory Status{context_str}:")
            log.info(f"  Total: {memory_info['total_gb']:.1f} GB")
            log.info(f"  Allocated: {memory_info['allocated_gb']:.1f} GB")
            log.info(f"  Reserved: {memory_info['reserved_gb']:.1f} GB")
            log.info(f"  Free: {memory_info['free_gb']:.1f} GB")
            log.info(f"  Utilization: {memory_info['utilization_percent']:.1f}%")
        else:
            context_str = f" ({context})" if context else ""
            log.info(f"GPU Memory Status{context_str}: No CUDA available")
    
    @staticmethod
    def cleanup_gpu_memory(aggressive: bool = False):
        """Clean up GPU memory with optional aggressive cleanup"""
        try:
            # Python garbage collection
            gc.collect()
            
            if torch.cuda.is_available():
                # Clear CUDA cache
                torch.cuda.empty_cache()
                
                if aggressive:
                    # Additional aggressive cleanup
                    torch.cuda.synchronize()
                    torch.cuda.ipc_collect()
                    
                log.info("GPU memory cleanup completed")
                return True
        except Exception as e:
            log.warning(f"GPU memory cleanup failed: {e}")
            return False
    
    @staticmethod
    def force_memory_reset():
        """Force a complete GPU memory reset (experimental)"""
        try:
            if torch.cuda.is_available():
                # Clear all cached memory
                torch.cuda.empty_cache()
                
                # Force garbage collection multiple times
                for _ in range(3):
                    gc.collect()
                    torch.cuda.empty_cache()
                
                # Synchronize and collect IPC resources
                torch.cuda.synchronize()
                torch.cuda.ipc_collect()
                
                log.info("Force GPU memory reset completed")
                return True
        except Exception as e:
            log.error(f"Force GPU memory reset failed: {e}")
            return False
    
    @staticmethod
    def check_memory_leak(expected_free_gb: float = 35.0) -> bool:
        """Check if there's a potential memory leak"""
        memory_info = GPUMemoryMonitor.get_gpu_memory_info()
        if not memory_info:
            return False
            
        if memory_info['free_gb'] < expected_free_gb:
            log.warning(f"Potential memory leak detected!")
            log.warning(f"Expected free: {expected_free_gb:.1f} GB, Actual free: {memory_info['free_gb']:.1f} GB")
            log.warning(f"Allocated: {memory_info['allocated_gb']:.1f} GB, Reserved: {memory_info['reserved_gb']:.1f} GB")
            return True
        else:
            log.info(f"Memory usage normal: {memory_info['free_gb']:.1f} GB free (expected: {expected_free_gb:.1f} GB)")
            return False