"""
plugins/voice.py
TTS (Piper) + STT (faster-whisper) integrated.
- TTS: reads aloud PyLine output when voice is ON
- STT: listens to mic when voice is ON and pyline is idle
- Silence for 5s -> sends transcribed text as input
- Voice OFF -> text only, no mic, no TTS
"""

import os
import re
import json
import threading
import queue
import time
from pathlib import Path
from typing import Dict, Any


# ===================================================
# PATHS
# ===================================================

def _voices_dir() -> Path:
    return Path(__file__).parent.parent / "voices"

def _pytemp() -> Path:
    p = Path.home() / ".pytemp"
    p.mkdir(exist_ok=True)
    return p

def _settings_file() -> Path:
    return _pytemp() / "settings.json"

def _load_settings() -> dict:
    f = _settings_file()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def _save_settings(data: dict):
    _settings_file().write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ===================================================
# VOICE MAP
# ===================================================

VOICE_MAP = {
    "female_ita":  "fe_IT.onnx",
    "femmina_ita": "fe_IT.onnx",
    "female ita":  "fe_IT.onnx",
    "femmina ita": "fe_IT.onnx",
    "fe_it":       "fe_IT.onnx",
    "paola":       "fe_IT.onnx",

    "female_eng":  "fe_US.onnx",
    "femmina_eng": "fe_US.onnx",
    "female eng":  "fe_US.onnx",
    "femmina eng": "fe_US.onnx",
    "fe_us":       "fe_US.onnx",
    "libritts":    "fe_US.onnx",

    "male_eng":    "man_US.onnx",
    "maschio_eng": "man_US.onnx",
    "male eng":    "man_US.onnx",
    "maschio eng": "man_US.onnx",
    "man_us":      "man_US.onnx",
    "ryan":        "man_US.onnx",
}

VOICE_LABELS = {
    "fe_IT.onnx":  "Female Italian (Paola)",
    "fe_US.onnx":  "Female English (LibriTTS)",
    "man_US.onnx": "Male English (Ryan)",
}


# ===================================================
# CLEAN TEXT FOR TTS
# ===================================================

_EMOJI_PATTERN = re.compile(
    "[\U00002600-\U000027FF"
    "\U0001F300-\U0001F9FF"
    "\U00002702-\U000027B0"
    "\U0000FE00-\U0000FE0F"
    "\U00010000-\U0010FFFF"
    "\U000024C2-\U0001F251]+",
    flags=re.UNICODE
)

_SKIP_PATTERNS = [
    re.compile(r"^pyline>\s*$"),
    re.compile(r"^-{3,}"),
    re.compile(r"^={3,}"),
    re.compile(r"^\s*\[.*\]\s*$"),
    re.compile(r"llama_"),
    re.compile(r"^\s*$"),
    re.compile(r"^gguf|^llm|^avx|^metal"),
    re.compile(r"^\[TTS\]"),
]

def clean_for_tts(text: str) -> str:
    text = _EMOJI_PATTERN.sub("", text)
    text = re.sub(r"[*_`#|\\]", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"^\s*[-•>]+\s*", "", text.strip())
    return text.strip()

def should_skip(text: str) -> bool:
    t = text.strip()
    if not t or len(t) <= 2:
        return True
    for pat in _SKIP_PATTERNS:
        if pat.search(t):
            return True
    return False


# ===================================================
# GLOBAL STATE
# ===================================================





# ===================================================
# PIPER TTS ENGINE
# ===================================================

class PiperTTS:
    def __init__(self):
        self._tts_queue: queue.Queue = queue.Queue()
        self._tts_thread: threading.Thread | None = None
        self._running = False
        self._voice_file: str | None = None
        self._voice_json: str | None = None
        self._enabled = False
        self._speaking = False  # True while TTS is playing audio

    def _load_state(self):
        s = _load_settings()
        self._enabled = s.get("voice_enabled", False)
        voice_key = s.get("voice", "female_ita")
        onnx = VOICE_MAP.get(voice_key.lower(), "fe_IT.onnx")
        candidate = _voices_dir() / onnx
        if candidate.exists():
            self._voice_file = str(candidate)
            json_name = onnx.replace(".onnx", ".json")
            json_candidate = _voices_dir() / json_name
            self._voice_json = str(json_candidate) if json_candidate.exists() else None
        else:
            self._voice_file = None
            self._voice_json = None

    def _save_state(self):
        s = _load_settings()
        s["voice_enabled"] = self._enabled
        current_onnx = Path(self._voice_file).name if self._voice_file else "fe_IT.onnx"
        for k, v in VOICE_MAP.items():
            if v == current_onnx:
                s["voice"] = k
                break
        _save_settings(s)

    def start(self):
        self._load_state()
        if not self._running:
            self._running = True
            self._tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
            self._tts_thread.start()

    def stop(self):
        self._running = False
        self._tts_queue.put(None)

    # ── TTS ─────────────────────────────────────────────────

    def speak(self, text: str):
        """Add text to TTS queue. Only when voice is enabled."""
        if not self._enabled:
            return
        if should_skip(text):
            return
        clean = clean_for_tts(text)
        if clean:
            self._tts_queue.put(clean)

    def _tts_worker(self):
        while self._running:
            try:
                text = self._tts_queue.get(timeout=1)
                if text is None:
                    break
                self._speaking = True
                self._synthesize(text)
                self._speaking = False
            except queue.Empty:
                continue
            except Exception:
                self._speaking = False

    def _synthesize(self, text: str):
        if not self._voice_file or not self._voice_json:
            return
        try:
            from piper import PiperVoice
            import sounddevice as sd
            import numpy as np
            import wave, io

            voice = PiperVoice.load(self._voice_file, config_path=self._voice_json)

            buf = io.BytesIO()
            with wave.open(buf, 'wb') as wf:
                voice.synthesize_wav(text, wf)

            buf.seek(0)
            with wave.open(buf, 'rb') as wf:
                raw = wf.readframes(wf.getnframes())
                rate = wf.getframerate()

            if raw:
                audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                sd.play(audio, samplerate=rate, blocking=True)

        except ImportError as e:
            print(f"   [TTS] missing library: {e}")
        except Exception as e:
            print(f"   [TTS] error: {e}")

    # ── STT ─────────────────────────────────────────────────

    # ── Public controls ──────────────────────────────────────

    def enable(self, voice_key: str | None = None):
        if voice_key:
            onnx = VOICE_MAP.get(voice_key.lower().strip())
            if not onnx:
                print(f"   Voice not found: '{voice_key}'")
                print(f"   Available: {', '.join(sorted(set(VOICE_MAP.keys())))}")
                return
            candidate = _voices_dir() / onnx
            if not candidate.exists():
                print(f"   Missing voice file: {candidate}")
                return
            self._voice_file = str(candidate)
            json_name = onnx.replace(".onnx", ".json")
            json_candidate = _voices_dir() / json_name
            self._voice_json = str(json_candidate) if json_candidate.exists() else None
            if not self._voice_json:
                print(f"   Missing json: {json_name} in voices/")
                return

        self._enabled = True
        self._save_state()
        label = VOICE_LABELS.get(Path(self._voice_file).name if self._voice_file else "", "unknown")
        print(f"   Voice ON - {label}")
        print("   Testing voice...")
        self._synthesize("Voice active.")
        print("   Voice test done.")

    def disable(self):
        self._enabled = False
        self._save_state()
        print("   Voice OFF")

    def status(self) -> dict:
        label = VOICE_LABELS.get(Path(self._voice_file).name if self._voice_file else "", "none")
        return {
            "enabled": self._enabled,
            "voice":   label,
            "voice_file": self._voice_file or "not set",
        }


# ===================================================
# SINGLETON
# ===================================================

_tts: PiperTTS | None = None

def get_tts() -> PiperTTS:
    global _tts
    if _tts is None:
        _tts = PiperTTS()
        _tts.start()
    return _tts

def speak(text: str):
    """Global speak — called by pyline after every print."""
    get_tts().speak(text)


# ===================================================
# ACTIONS
# ===================================================

def set_voice(args: Dict[str, Any], workspace, safe_resolve) -> Dict[str, Any]:
    action = (args.get("action") or "on").lower().strip()
    tts = get_tts()

    if action in ("on", "enable", "attiva", "accendi"):
        voice = args.get("voice") or args.get("name") or None
        tts.enable(voice)
        return {"status": "ok", "enabled": True}

    elif action in ("off", "disable", "disattiva", "spegni"):
        tts.disable()
        return {"status": "ok", "enabled": False}

    elif action in ("status", "stato"):
        s = tts.status()
        print(f"   Voice: {'ON' if s['enabled'] else 'OFF'} - {s['voice']}")
        return {"status": "ok", **s}

    elif action in ("list", "lista", "voci"):
        print("   Available voices:")
        for onnx, label in VOICE_LABELS.items():
            path = _voices_dir() / onnx
            exists = "ok" if path.exists() else "missing"
            keys = [k for k, v in VOICE_MAP.items() if v == onnx]
            print(f"   - {label}: {exists}")
            print(f"     Keywords: {', '.join(keys[:4])}")
        return {"status": "ok"}

    return {"error": "unknown_action", "reason": "Use: on, off, status, list"}


# ===================================================
# REGISTER
# ===================================================

def register_actions():
    get_tts()
    return {
        "set_voice": set_voice,
    }