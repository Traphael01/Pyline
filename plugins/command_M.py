"""
plugins/command_M.py
Memoria persistente + Sistema Sveglie di PyLine
- Memoria salvata in ~/.pytemp/memory.json
- Sveglie salvate in ~/.pytemp/alarms.json
- All'ora X: gif gorilla fullscreen sopra a tutto + suoneria mp3
"""

import json
import re
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any

# ===================================================
# PATH UTILITY
# ===================================================

def _pytemp() -> Path:
    p = Path.home() / ".pytemp"
    p.mkdir(exist_ok=True)
    try:
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(p), 0x02)
    except Exception:
        pass
    return p

def _avgif_dir() -> Path:
    """Trova la cartella avgif relativa a command_M.py"""
    return Path(__file__).parent.parent / "avgif"

def _memory_file() -> Path:
    return _pytemp() / "memory.json"

def _alarms_file() -> Path:
    return _pytemp() / "alarms.json"

def _settings_file() -> Path:
    return _pytemp() / "settings.json"

# ===================================================
# LOAD / SAVE
# ===================================================

def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def _save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# ===================================================
# MEMORIA
# ===================================================

def _extract_kv(text: str):
    t = text.strip()
    tl = t.lower()
    patterns = [
        (r"mi chiamo\s+(.+)",             "nome"),
        (r"il mio nome [eè]\s+(.+)",      "nome"),
        (r"ho\s+(\d+)\s+anni",            "età"),
        (r"abito a\s+(.+)",               "città"),
        (r"vivo a\s+(.+)",                "città"),
        (r"il mio cane si chiama\s+(.+)", "cane"),
        (r"il mio gatto si chiama\s+(.+)","gatto"),
        (r"lavoro (come|da)\s+(.+)",      "lavoro"),
    ]
    for pattern, key in patterns:
        m = re.search(pattern, tl)
        if m:
            value = m.group(m.lastindex).strip().rstrip(".,!?")
            return key, value
    return "info", t

def set_memory(args: Dict[str, Any], workspace, safe_resolve) -> Dict[str, Any]:
    text = args.get("content") or args.get("context") or ""
    if not text:
        return {"status": "error", "reason": "missing_content"}
    key, value = _extract_kv(text)
    data = _load_json(_memory_file())
    data[key] = {
        "value": value,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "raw": text,
    }
    _save_json(_memory_file(), data)
    print(f"   💾 Memorizzato: {key} = {value}")
    return {"status": "ok", "stored": {key: value}}

def get_memory(args: Dict[str, Any], workspace, safe_resolve) -> Dict[str, Any]:
    data = _load_json(_memory_file())
    if not data:
        return {"status": "ok", "memory": {}, "message": "Nessuna memoria salvata"}
    print("\n   🧠 Memoria PyLine:")
    for k, v in data.items():
        val = v["value"] if isinstance(v, dict) else v
        saved = v.get("saved_at", "") if isinstance(v, dict) else ""
        print(f"   • {k}: {val}  [{saved}]")
    return {"status": "ok", "memory": {k: v["value"] if isinstance(v, dict) else v for k, v in data.items()}}

def clear_memory(args: Dict[str, Any], workspace, safe_resolve) -> Dict[str, Any]:
    _save_json(_memory_file(), {})
    print("   🧹 Memoria cancellata")
    return {"status": "ok", "cleared": True}

# ===================================================
# SUONERIA
# ===================================================

def _get_ringtone() -> str:
    """Restituisce il nome del file suoneria (default: samsung.mp3)"""
    settings = _load_json(_settings_file())
    return settings.get("ringtone", "samsung.mp3")

def set_ringtone(args: Dict[str, Any], workspace, safe_resolve) -> Dict[str, Any]:
    """Cambia la suoneria delle sveglie (samsung.mp3 o brain.mp3)"""
    name = args.get("ringtone") or args.get("name") or ""
    valid = {"samsung.mp3", "brain.mp3"}
    if name not in valid:
        return {"status": "error", "reason": f"Suonerie disponibili: {', '.join(valid)}"}
    settings = _load_json(_settings_file())
    settings["ringtone"] = name
    _save_json(_settings_file(), settings)
    print(f"   🔔 Suoneria impostata: {name}")
    return {"status": "ok", "ringtone": name}

# ===================================================
# ALARM DISPLAY (gif + audio)
# ===================================================

def _show_alarm(label: str):
    """Mostra gif gorilla fullscreen sopra a tutto + suoneria. Blocca finché l'utente chiude."""
    avgif = _avgif_dir()
    gif_path  = avgif / "gorilla.gif"
    audio_path = avgif / _get_ringtone()

    # --- Audio in thread separato ---
    def play_audio():
        import os
        os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
        import pygame
        pygame.mixer.init()
        if audio_path.exists():
            pygame.mixer.music.load(str(audio_path))
            pygame.mixer.music.play(-1)  # loop infinito

    audio_thread = threading.Thread(target=play_audio, daemon=True)
    audio_thread.start()

    # --- GUI tkinter fullscreen sopra a tutto ---
    import tkinter as tk
    from PIL import Image, ImageTk

    root = tk.Tk()
    root.title(f"⏰ {label}")
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)      # sopra a tutto
    root.configure(bg="black")
    root.lift()
    root.focus_force()

    # Carica frame gif
    frames = []
    if gif_path.exists():
        img = Image.open(str(gif_path))
        orig_w, orig_h = img.size
        new_w, new_h = orig_w * 2, orig_h * 2
        try:
            while True:
                frame = img.copy().convert("RGBA").resize((new_w, new_h), Image.NEAREST)
                frames.append(ImageTk.PhotoImage(frame))
                img.seek(img.tell() + 1)
        except EOFError:
            pass

    label_widget = tk.Label(root, bg="black")
    label_widget.pack(expand=True)

    # Label testo sveglia
    tk.Label(
        root, text=f"⏰  {label}",
        font=("Arial", 36, "bold"), fg="white", bg="black"
    ).pack(pady=10)

    tk.Label(
        root, text="[ premi ESC o clicca per chiudere ]",
        font=("Arial", 16), fg="gray", bg="black"
    ).pack()

    # Animazione loop
    frame_idx = [0]
    def animate():
        if frames:
            label_widget.config(image=frames[frame_idx[0]])
            frame_idx[0] = (frame_idx[0] + 1) % len(frames)
        root.after(50, animate)  # ~20fps

    def close(_=None):
        import os
        os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
        import pygame
        pygame.mixer.music.stop()
        pygame.mixer.quit()
        root.destroy()

    root.bind("<Escape>", close)
    root.bind("<Button-1>", close)

    animate()
    root.mainloop()

# ===================================================
# ALARM CHECKER (thread in background)
# ===================================================

_alarm_thread_running = False

def _alarm_checker():
    """Controlla ogni 30 secondi se c'è una sveglia da attivare."""
    global _alarm_thread_running
    while _alarm_thread_running:
        now = datetime.now()
        alarms = _load_json(_alarms_file())
        changed = False

        for alarm_id, alarm in list(alarms.items()):
            if alarm.get("fired"):
                continue
            try:
                alarm_dt = datetime.strptime(alarm["datetime"], "%Y-%m-%d %H:%M")
            except Exception:
                continue

            # Sveglia scaduta senza pyline attivo → cancella
            if alarm_dt < now - timedelta(minutes=5):
                print(f"\n   ⏰ Sveglia '{alarm['label']}' scaduta — rimossa")
                del alarms[alarm_id]
                changed = True
                continue

            # È ora! (entro 1 minuto)
            if abs((alarm_dt - now).total_seconds()) <= 60:
                alarm["fired"] = True
                changed = True
                print(f"\n   🔔 SVEGLIA: {alarm['label']}")
                # Mostra in thread separato per non bloccare il checker
                t = threading.Thread(target=_show_alarm, args=(alarm["label"],), daemon=True)
                t.start()

        if changed:
            _save_json(_alarms_file(), alarms)

        time.sleep(30)

def start_alarm_thread():
    """Avvia il thread checker in background. Chiamato da pyline all'avvio."""
    global _alarm_thread_running
    if not _alarm_thread_running:
        _alarm_thread_running = True
        t = threading.Thread(target=_alarm_checker, daemon=True)
        t.start()
        print("   ⏰ Sistema sveglie attivo")

# ===================================================
# AZIONI SVEGLIE
# ===================================================

def set_alarm(args: Dict[str, Any], workspace, safe_resolve) -> Dict[str, Any]:
    """
    Imposta una sveglia.
    args: {
      "datetime": "2025-03-03 14:30"  oppure
      "time": "14:30"                  (oggi o domani automaticamente)
      "label": "Prendi le medicine"
    }
    """
    label = args.get("label") or args.get("name") or "Sveglia"
    dt_str = args.get("datetime") or ""
    time_str = args.get("time") or ""

    # Parsing orario
    if dt_str:
        try:
            alarm_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        except Exception:
            return {"status": "error", "reason": f"Formato datetime non valido: usa 'YYYY-MM-DD HH:MM'"}
    elif time_str:
        try:
            t = datetime.strptime(time_str, "%H:%M")
            alarm_dt = datetime.now().replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
            if alarm_dt < datetime.now():
                alarm_dt += timedelta(days=1)  # domani
        except Exception:
            return {"status": "error", "reason": f"Formato ora non valido: usa 'HH:MM'"}
    else:
        return {"status": "error", "reason": "Specifica 'datetime' o 'time'"}

    alarms = _load_json(_alarms_file())
    alarm_id = f"alarm_{int(datetime.now().timestamp())}"
    alarms[alarm_id] = {
        "label": label,
        "datetime": alarm_dt.strftime("%Y-%m-%d %H:%M"),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fired": False,
    }
    _save_json(_alarms_file(), alarms)

    when = alarm_dt.strftime("%d/%m/%Y alle %H:%M")
    print(f"   ⏰ Sveglia impostata: '{label}' — {when}")
    return {"status": "ok", "alarm": label, "when": when, "id": alarm_id}


def list_alarms(args: Dict[str, Any], workspace, safe_resolve) -> Dict[str, Any]:
    """Mostra tutte le sveglie attive."""
    alarms = _load_json(_alarms_file())
    active = {k: v for k, v in alarms.items() if not v.get("fired")}

    if not active:
        print("   ⏰ Nessuna sveglia attiva")
        return {"status": "ok", "alarms": []}

    print("\n   ⏰ Sveglie attive:")
    result = []
    for aid, a in active.items():
        print(f"   • [{aid}] '{a['label']}' — {a['datetime']}")
        result.append({"id": aid, "label": a["label"], "datetime": a["datetime"]})
    return {"status": "ok", "alarms": result}


def delete_alarm(args: Dict[str, Any], workspace, safe_resolve) -> Dict[str, Any]:
    """Cancella una sveglia per ID o label."""
    alarm_id = args.get("id") or ""
    label    = args.get("label") or ""
    alarms   = _load_json(_alarms_file())

    if alarm_id and alarm_id in alarms:
        del alarms[alarm_id]
        _save_json(_alarms_file(), alarms)
        print(f"   🗑️  Sveglia '{alarm_id}' cancellata")
        return {"status": "ok", "deleted": alarm_id}

    if label:
        to_delete = [k for k, v in alarms.items() if v["label"].lower() == label.lower()]
        for k in to_delete:
            del alarms[k]
        _save_json(_alarms_file(), alarms)
        print(f"   🗑️  Sveglie '{label}' cancellate: {len(to_delete)}")
        return {"status": "ok", "deleted": len(to_delete)}

    return {"status": "error", "reason": "Specifica 'id' o 'label'"}


# ===================================================
# REGISTER
# ===================================================

def register_actions():
    # Avvia il checker in background appena il plugin viene caricato
    start_alarm_thread()
    return {
        "set_memory":    set_memory,
        "get_memory":    get_memory,
        "clear_memory":  clear_memory,
        "set_alarm":     set_alarm,
        "list_alarms":   list_alarms,
        "delete_alarm":  delete_alarm,
        "set_ringtone":  set_ringtone,
    }