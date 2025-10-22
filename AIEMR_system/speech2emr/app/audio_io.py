# app/audio_io.py
import numpy as np, soundfile as sf
from math import gcd
try:
    from scipy.signal import resample_poly
    _HAS_SCIPY = True
except Exception:
    _HAS_SCIPY = False

def _resample_to_16k(wav: np.ndarray, sr: int, target=16_000):
    if sr == target:
        return wav.astype(np.float32, copy=False), sr
    if _HAS_SCIPY:
        up, down = target // gcd(sr, target), sr // gcd(sr, target)
        return resample_poly(wav, up, down).astype(np.float32), target
    # fallback
    x_old = np.linspace(0, 1, num=len(wav), endpoint=False, dtype=np.float64)
    x_new = np.linspace(0, 1, num=int(len(wav) * target / sr), endpoint=False, dtype=np.float64)
    return np.interp(x_new, x_old, wav).astype(np.float32), target

def load_and_preprocess_to_16k_mono(path: str, target_sr=16_000):
    wav, sr = sf.read(path, dtype="float32", always_2d=False)
    if wav.ndim > 1:
        wav = wav.mean(axis=-1)  # mono
    wav, sr = _resample_to_16k(wav, sr, target_sr)
    return wav, sr
