import os
import sys
import argparse
import importlib
import pkgutil
import json
import re
import getpass

# TTS helper - uses already-loaded singleton from voice plugin
_tts_singleton = None

def _speak(text: str):
    global _tts_singleton
    try:
        if _tts_singleton is None:
            from plugins.voice import get_tts
            _tts_singleton = get_tts()
        _tts_singleton.speak(text)
    except Exception:
        pass
import subprocess
import traceback
from pathlib import Path
from typing import Dict, Any, Callable

# === Config ===
DEFAULT_WORKSPACE = Path.home() / "PyLineWorkspace"
PLUGINS_PACKAGE = "plugins"
MODEL_DIR = Path("./models")

ALLOWED_ACTIONS = {
    "open_app", "open_url", "open_dir", "open_media", "open_file",
    "create_folder", "create_file", "write_file", "fix_file", "rename_file",
    "delete_file", "delete_folder", "copy_file", "move_file",
    "create_docx", "create_xlsx", "create_pptx", "create_pdf",
    "set_brightness", "set_voice",
    "take_screenshot", "analyze_screen",
    "list_processes", "kill_process", "get_temps", "clean_system",
    "search_files", "explore_files",
    "list_settings_shortcuts", "open_system_setting",
    "set_memory", "get_memory", "clear_memory",
    "set_alarm", "list_alarms", "delete_alarm", "set_ringtone",
    "generate_project", "compile_project", "analyze_url",
    "run_command", "get_system_info",
}

# ===================================================
# GPU DETECTION & SELECTION
# ===================================================

def detect_gpus() -> list[dict]:
    gpus = []
    try:
        import torch
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                gpus.append({"index": i, "name": torch.cuda.get_device_name(i)})
            return gpus
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.split(",", 1)
                if len(parts) == 2:
                    gpus.append({"index": int(parts[0].strip()), "name": parts[1].strip()})
    except Exception:
        pass
    return gpus


def select_device(gpus: list[dict]) -> dict:
    if not gpus:
        print("   No CUDA GPU detected — using CPU.")
        return {"type": "cpu"}

    print("\n   GPUs detected:")
    for g in gpus:
        print(f"   {g['index']}) {g['name']}")

    if len(gpus) == 1:
        print(f"\n   Use GPU '{gpus[0]['name']}' or CPU?")
        print("   g) GPU   c) CPU")
        while True:
            choice = input("Scelta: ").strip().lower()
            if choice in ("g", "gpu"):
                print(f"   Using GPU: {gpus[0]['name']}")
                return {"type": "gpu", "index": gpus[0]["index"], "name": gpus[0]["name"]}
            elif choice in ("c", "cpu"):
                print("   Using CPU.")
                return {"type": "cpu"}
    else:
        print("\n   Select device:")
        for g in gpus:
            print(f"   {g['index']}) GPU — {g['name']}")
        print("   c) CPU")
        valid = {str(g["index"]) for g in gpus}
        while True:
            choice = input("Scelta (numero GPU o 'c'): ").strip().lower()
            if choice == "c":
                print("   Using CPU.")
                return {"type": "cpu"}
            elif choice in valid:
                idx = int(choice)
                gpu = next(g for g in gpus if g["index"] == idx)
                print(f"   Using GPU [{idx}]: {gpu['name']}")
                return {"type": "gpu", "index": idx, "name": gpu["name"]}


# ===================================================
# MODEL LOADING
# ===================================================

def _choose_n_ctx(device: dict) -> int:
    """Sceglie n_ctx in base alla RAM e se la GPU è davvero attiva."""
    if device["type"] == "gpu":
        # Verifica che CUDA funzioni davvero
        try:
            import torch
            if torch.cuda.is_available():
                return 10240
        except ImportError:
            pass
        # GPU rilevata ma CUDA non funziona — usa RAM
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / 1e9
        if ram_gb < 8:
            return 4096
        elif ram_gb <= 16:
            return 8192
        else:
            return 10240
    except ImportError:
        return 6144


def load_model(device: dict):
    gguf_files = list(MODEL_DIR.rglob("*.gguf"))
    if not gguf_files:
        print("   No GGUF model found in ./models")
        print("   Run download_Model.py first")
        sys.exit(1)

    model_path = str(gguf_files[0])
    print(f"   Loading model: {Path(model_path).name}")

    from llama_cpp import Llama

    n_gpu_layers = -1 if device["type"] == "gpu" else 0
    main_gpu = device.get("index", 0) if device["type"] == "gpu" else 0
    n_ctx = _choose_n_ctx(device)
    print(f"   Context window: {n_ctx} tokens")

    llm = Llama(
        model_path=model_path,
        n_ctx=n_ctx,
        n_gpu_layers=n_gpu_layers,
        main_gpu=main_gpu,
        verbose=False,
    )

    device_label = f"GPU [{main_gpu}]" if device["type"] == "gpu" else "CPU"
    print(f"   Model ready on {device_label}.\n")
    return llm


# ===================================================
# SYSTEM PROMPT
# ===================================================

def build_system_prompt() -> str:
    username = getpass.getuser()
    return f"""You are PyLine, an AI assistant that controls a Windows PC for user "{username}".

RULES:
1. If the user gives a PC command, respond with ONLY a JSON object or JSON array, nothing else.
2. If the user is chatting or asking a question, respond normally in their language.
3. NEVER add explanations around JSON. NEVER wrap JSON in markdown backticks.
4. For multiple sequential actions, use a JSON array.

SINGLE ACTION FORMAT: {{"action": "action_name", "args": {{}}}}
MULTI ACTION FORMAT: [{{"action": "action1", "args": {{}}}}, {{"action": "action2", "args": {{}}}}]

ACTIONS:
- open_app: args={{"app": "app name"}}
- open_url: args={{"url": "full url with https://"}}
- open_dir: args={{"path": "folder alias or path"}}
- open_media: args={{"path": "file path"}}
- create_folder: args={{"path": "folder alias or path"}}
- create_file: args={{"path": "path", "content": "file content"}}
- write_file: args={{"path": "path", "content": "text"}}
- fix_file: args={{"path": "file path", "changes": "what to change"}}
- rename_file: args={{"path": "current path", "new_name": "new filename only"}}
- delete_file: args={{"path": "file path"}}
- delete_folder: args={{"path": "folder path"}}
- copy_file: args={{"src": "source path", "dst": "destination path"}}
- move_file: args={{"src": "source path", "dst": "destination path"}}
- search_files: args={{"query": "what to find"}}
- explore_files: args={{"mode": "top_large|recent|downloads"}}
- open_system_setting: args={{"key": "setting name"}}
- set_alarm: args={{"time": "HH:MM", "label": "descrizione"}} oppure args={{"datetime": "YYYY-MM-DD HH:MM", "label": "descrizione"}}
- list_alarms: args={{}}
- delete_alarm: args={{"id": "alarm_id"}} oppure args={{"label": "nome sveglia"}}
- set_ringtone: args={{"ringtone": "samsung.mp3"}} oppure args={{"ringtone": "brain.mp3"}}
- set_memory: args={{"content": "info to remember"}}
- get_memory: args={{}}
- clear_memory: args={{}}
- analyze_url: args={{"url": "url"}} ← analyze URL without opening it
- generate_project: args={{"name": "name", "description": "what to build", "technologies": ["python"], "compile": false}} ← set compile=true to also build .exe
- compile_project: args={{"path": "project folder path"}} ← compile existing Python project to .exe
- run_command: args={{"cmd": "shell command"}}
- get_system_info: args={{}}
- set_brightness: args={{"level": 70}} oppure args={{"action": "get"}}
- take_screenshot: args={{"path": "desktop/screen.png"}}
- analyze_screen: args={{"question": "cosa c'e scritto in alto?"}} <- analisi schermo con AI Vision
- list_processes: args={{"sort": "cpu", "limit": 10}}
- kill_process: args={{"name": "chrome.exe"}} oppure args={{"pid": 1234}}
- get_temps: args={{}}
- clean_system: args={{}} — cleans Windows temp, program Temp folders, reports heaviest apps
- set_voice: args={{"action": "on", "voice": "female_ita"}} / {{"action": "off"}} / {{"action": "status"}} / {{"action": "list"}}
  voice options: female_ita, female_eng, male_eng
- create_docx: args={{"path": "desktop/doc.docx", "title": "Title", "content": [{{"type": "heading", "text": "...", "level": 1}}, {{"type": "paragraph", "text": "..."}}]}}
- create_xlsx: args={{"path": "desktop/table.xlsx", "sheets": [{{"name": "Sheet1", "headers": ["A","B"], "rows": [[1,2],[3,4]]}}]}}
- create_pptx: args={{"path": "desktop/slides.pptx", "slides": [{{"type": "title", "title": "...", "subtitle": "..."}}, {{"type": "content", "title": "...", "bullets": ["point1", "point2"]}}]}}
- create_pdf: args={{"path": "desktop/doc.pdf", "title": "Title", "content": [{{"type": "paragraph", "text": "..."}}]}}

IMPORTANT OFFICE RULES:
- User says "crea presentazione/slide/pptx" -> ALWAYS use create_pptx, NEVER generate_project
- User says "crea word/documento/docx" -> ALWAYS use create_docx, NEVER generate_project
- User says "crea excel/foglio/xlsx" -> ALWAYS use create_xlsx, NEVER generate_project
- User says "crea pdf" -> ALWAYS use create_pdf, NEVER generate_project
- generate_project is ONLY for code projects (Python, C++, web apps, games, etc.)

PATH ALIASES (resolved automatically by the system):
- "desktop/..." → Desktop (OneDrive or normal, auto-detected)
- "downloads/..." → Downloads
- "documents/..." → Documents
- "pictures/..." → Pictures
- "music/..." → Music
- "videos/..." → Videos
- "home/..." → Home folder
- "workspace/..." → PyLineWorkspace

EXAMPLES:
User: "crea file desktop/ciao.txt con scritto ciao"
Response: {{"action": "create_file", "args": {{"path": "desktop/ciao.txt", "content": "ciao"}}}}

User: "rinomina ciao.txt in limbo.txt e scrivi ciao dentro"
Response: [{{"action": "rename_file", "args": {{"path": "desktop/ciao.txt", "new_name": "limbo.txt"}}}}, {{"action": "write_file", "args": {{"path": "desktop/limbo.txt", "content": "ciao"}}}}]

User: "genera un gioco platformer python e dopo compilalo in exe"
Response: {{"action": "generate_project", "args": {{"name": "platformer", "description": "platformer game with jump gravity and coins", "technologies": ["python", "pygame"], "compile": true}}}}

User: "compila il progetto in workspace/platformer"
Response: {{"action": "compile_project", "args": {{"path": "workspace/platformer"}}}}

User: "che risorse sta usando il pc?"
Response: {{"action": "get_system_info", "args": {{}}}}

User: "crea una presentazione su python"
Response: {{"action": "create_pptx", "args": {{"path": "desktop/presentazione_python.pptx", "slides": [{{"type": "title", "title": "Python", "subtitle": "Panoramica del linguaggio"}}, {{"type": "content", "title": "Caratteristiche", "bullets": ["Semplice e leggibile", "Multi-paradigma", "Grande ecosistema di librerie"]}}]}}}}

User: "fai un documento word con la lista della spesa"
Response: {{"action": "create_docx", "args": {{"path": "desktop/lista_spesa.docx", "title": "Lista della spesa", "content": [{{"type": "heading", "text": "Da comprare", "level": 1}}, {{"type": "bullet", "items": ["Latte", "Pane", "Uova"]}}]}}}}

User: "crea un excel con nomi ed eta"
Response: {{"action": "create_xlsx", "args": {{"path": "desktop/persone.xlsx", "sheets": [{{"name": "Persone", "headers": ["Nome", "Eta"], "rows": []}}]}}}}

User: "ciao come stai"
Response: Ciao! Sto bene, come posso aiutarti?"""


# ===================================================
# UTILITY
# ===================================================

def ensure_workspace(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def safe_resolve(path: Path, workspace: Path) -> Path:
    p = path.expanduser().resolve()
    if not p.is_absolute():
        p = (workspace / p).resolve()
    return p


# ===================================================
# PLUGIN LOADER
# ===================================================

def load_plugins(llm=None) -> Dict[str, Callable]:
    actions = {}
    try:
        import plugins as _plugins_pkg
    except Exception as e:
        print(f"   No plugins package found: {e}")
        return actions

    for _, name, _ in pkgutil.iter_modules(_plugins_pkg.__path__):
        if name in ("command_P",):
            continue
        full = f"{PLUGINS_PACKAGE}.{name}"
        try:
            mod = importlib.import_module(full)
            if name in ("command_G", "command_sys", "voice") and llm is not None and hasattr(mod, "set_llm"):
                mod.set_llm(llm)
            if hasattr(mod, "register_actions"):
                reg = mod.register_actions()
                actions.update(reg)
                print(f"   Plugin loaded: {name}")
        except Exception as e:
            print(f"   Plugin error ({full}): {e}")
    return actions


# ===================================================
# PREPARSER
# ===================================================

def preparse_command(cmd: str):
    lower = cmd.lower()
    if re.search(r"\b(trova|cerca|dov[eè])\b", lower) and re.search(r"\b(file|immagin|foto|video|document|cartella)\b", lower):
        return {"action": "search_files", "args": {"query": cmd}}
    if re.search(r"\b(più grandi|pesanti|ultimi scaricati|recenti)\b", lower):
        return {"action": "explore_files", "args": {"query": cmd}}
    if re.search(r"\b(apri|mostra|riproduci)\b", lower) and re.search(r"\b(jpg|png|jpeg|gif|mp4|mp3|wav|foto|video|immagin)\b", lower):
        return {"action": "open_media", "args": {"path": cmd}}
    return None


# ===================================================
# BUILT-IN ACTIONS
# ===================================================

def _run_command(args: Dict[str, Any], workspace: Path, safe_resolve_fn) -> Dict[str, Any]:
    cmd = args.get("cmd", "")
    if not cmd:
        return {"error": "missing_cmd"}

    # Comandi bloccati per sicurezza
    BLOCKED = ["format", "del /f", "rmdir /s", "rd /s", "shutdown", "rm -rf",
               "gcc", "g++", "clang", "javac", "cargo build", "go build", "dotnet build", "cl "]
    for b in BLOCKED:
        if b in cmd.lower():
            return {"error": "blocked", "reason": f"'{b}' bloccato — usa 'genera un progetto' per compilare"}

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=30, cwd=str(workspace)
        )
        return {
            "status": "ok",
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": str(e)}


def _get_system_info(args: Dict[str, Any], workspace: Path, safe_resolve_fn) -> Dict[str, Any]:
    info = {}
    try:
        import psutil
        info["cpu_percent"] = psutil.cpu_percent(interval=1)
        info["cpu_cores"] = psutil.cpu_count()
        ram = psutil.virtual_memory()
        info["ram_total_gb"] = round(ram.total / 1e9, 1)
        info["ram_used_gb"] = round(ram.used / 1e9, 1)
        info["ram_percent"] = ram.percent
        disk = psutil.disk_usage("/")
        info["disk_total_gb"] = round(disk.total / 1e9, 1)
        info["disk_free_gb"] = round(disk.free / 1e9, 1)
    except ImportError:
        info["psutil"] = "non installato — esegui: pip install psutil"
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            info["gpus"] = result.stdout.strip().splitlines()
    except Exception:
        pass
    print(f"\n Info sistema: {json.dumps(info, indent=2)}\n")
    return {"status": "ok", "info": info}


def _compile_project(args: Dict[str, Any], workspace: Path, safe_resolve_fn) -> Dict[str, Any]:
    """Compila un progetto Python in .exe usando PyInstaller."""
    path = args.get("path", "")
    if not path:
        return {"error": "missing_path"}

    try:
        from plugins.io_actions import normalize_path
        project_path = normalize_path(path, workspace)
    except Exception:
        project_path = Path(path)

    if not project_path.exists():
        return {"error": "not_found", "path": str(project_path)}

    # Cerca main.py
    main_py = project_path / "main.py"
    if not main_py.exists():
        candidates = list(project_path.rglob("main.py"))
        if not candidates:
            return {"error": "no_main_py", "reason": "Nessun main.py trovato"}
        main_py = candidates[0]

    # Installa PyInstaller se mancante
    try:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--version"], capture_output=True, check=True)
    except Exception:
        print("  Installo PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    print(f"\n Compilazione: {project_path.name}")
    print("   Attendi 1-2 minuti...")

    dist_dir = project_path / "dist"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "PyInstaller",
             "--onefile",
             "--distpath", str(dist_dir),
             "--workpath", str(project_path / "build"),
             "--specpath", str(project_path),
             "--name", project_path.name,
             str(main_py)],
            capture_output=True, text=True, timeout=300,
            cwd=str(project_path)
        )
        if result.returncode == 0:
            exe = dist_dir / f"{project_path.name}.exe"
            if exe.exists():
                size = round(exe.stat().st_size / 1e6, 1)
                print(f" Compilato! {exe} ({size} MB)")
                return {"status": "ok", "exe": str(exe), "size_mb": size}
            return {"status": "ok", "dist": str(dist_dir)}
        else:
            return {"error": "compile_failed", "stderr": result.stderr[-800:]}
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": str(e)}


# ===================================================
# AI PARSER
# ===================================================

def ai_parse(llm, text: str, history: list):
    messages = [{"role": "system", "content": build_system_prompt()}] + history + [{"role": "user", "content": text}]

    try:
        resp = llm.create_chat_completion(messages=messages, max_tokens=512, temperature=0.1)
        out = resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  Errore modello: {e}")
        return None

    out_clean = re.sub(r"^```[a-zA-Z]*", "", out).strip()
    out_clean = re.sub(r"```$", "", out_clean).strip()

    match_array = re.search(r"\[.*\]", out_clean, re.DOTALL)
    if match_array:
        try:
            data = json.loads(match_array.group(0))
            if isinstance(data, list) and all("action" in d for d in data):
                return data
        except Exception:
            pass

    match_obj = re.search(r"\{.*\}", out_clean, re.DOTALL)
    if match_obj:
        try:
            return json.loads(match_obj.group(0))
        except Exception:
            pass

    print(f"\n PyLine: {out}\n")
    _speak(out)
    return None



# ===================================================
# PRETTY PRINT
# ===================================================

def pretty_print(action: str, out: dict):
    """Stampa il risultato in modo leggibile - niente JSON grezzo."""
    from pathlib import Path as _P

    res = out.get("result", out) if isinstance(out, dict) else out

    # Errore nel wrapper esterno
    if isinstance(out, dict) and out.get("status") == "cancelled":
        print("  ⏭  Operazione annullata.\n")
        return
    if isinstance(out, dict) and ("error" in out and "result" not in out):
        reason = out.get("reason") or out.get("error") or "motivo sconosciuto"
        print(f"   Si è verificato un errore durante: {action}")
        print(f"     Motivo: {reason}\n")
        return
    # Errore nel result interno
    if isinstance(res, dict) and res.get("error"):
        reason = res.get("reason") or res.get("error")
        print(f"   Si è verificato un errore durante: {action}")
        print(f"     Motivo: {reason}\n")
        return

    print()
    if action == "create_file":
        p = _P(res.get("created", "") or ".")
        print(f"   File creato")
        print(f"      Nome     : {p.name}")
        print(f"      Cartella : {p.parent}")
        print(f"      Tipo     : {p.suffix or 'nessuno'}")
    elif action == "write_file":
        p = _P(res.get("written", res.get("created", "")) or ".")
        print(f"   File scritto: {p.name}")
        print(f"      Cartella : {p.parent}")
    elif action == "create_folder":
        p = _P(res.get("created", "") or ".")
        print(f"   Cartella creata")
        print(f"      Nome     : {p.name}")
        print(f"      Percorso : {p.parent}")
    elif action == "delete_file":
        p = _P(res.get("deleted", "") or ".")
        backup = res.get("backup", "")
        print(f"   File eliminato: {p.name}")
        if backup: print(f"      Backup   : {_P(backup).name}")
    elif action == "delete_folder":
        p = _P(res.get("deleted", "") or ".")
        backup = res.get("backup", "")
        print(f"   Cartella eliminata: {p.name}")
        if backup: print(f"      Backup   : {_P(backup).name}")
    elif action == "rename_file":
        p = _P(res.get("renamed", "") or ".")
        print(f"   Rinominato in: {p.name}")
        print(f"      Cartella : {p.parent}")
    elif action == "copy_file":
        print(f"   File copiato in: {res.get('copied', '')}")
    elif action == "move_file":
        print(f"   File spostato in: {res.get('moved', '')}")
    elif action == "open_app":
        print(f"   Applicazione aperta: {str(res.get('result','')).replace('Aperto: ','')}")
    elif action == "open_url":
        print(f"   URL aperto nel browser")
    elif action == "open_dir":
        print(f"   Cartella aperta: {str(res.get('result','')).replace('Aperta: ','')}")
    elif action == "run_command":
        rc = res.get("returncode", 0)
        stdout = res.get("stdout", "")
        stderr = res.get("stderr", "")
        if rc == 0:
            print(f"   Comando eseguito")
            if stdout: print(f"     Output:\n{stdout[:400]}")
        else:
            print(f"    Comando terminato con errore (codice {rc})")
            if stderr: print(f"     {stderr[:300]}")
    elif action == "get_system_info":
        print("   Info sistema:")
        for k, v in res.items(): print(f"     • {k}: {v}")
    elif action == "generate_project":
        print(f"   Progetto generato")
        print(f"      Cartella   : {res.get('project', '')}")
        print(f"      Linguaggio : {res.get('language', '')}")
        print(f"      File creati: {len(res.get('created_files', []))}")
    elif action == "search_files":
        results = res.get("results", [])
        print(f"   Trovati {len(results)} file")
        for r in results[:5]: print(f"     • {r}")
        if len(results) > 5: print(f"     ... e altri {len(results)-5}")
    elif action == "fix_file":
        path = res.get("fixed", res.get("path", ""))
        print(f"   File modificato: {_P(path).name if path else ''}")
    elif action in ("create_docx", "create_xlsx", "create_pptx", "create_pdf"):
        icons = {"create_docx": "", "create_xlsx": "", "create_pptx": "", "create_pdf": ""}
        labels = {"create_docx": "Word", "create_xlsx": "Excel", "create_pptx": "PowerPoint", "create_pdf": "PDF"}
        p = _P(res.get("created", "") or ".")
        print(f"   {icons[action]} File {labels[action]} creato")
        print(f"      Nome     : {p.name}")
        print(f"      Cartella : {p.parent}")
    elif action == "set_brightness":
        level = res.get("level")
        emoji = "" if (level or 0)<20 else "" if (level or 0)<70 else ""
        print(f"   {emoji} Luminosita: {level}%")
    elif action == "take_screenshot":
        print(f"    Screenshot salvato: {_P(res.get('path','')).name}")
        print(f"      Dimensione: {res.get('size','')}")
    elif action == "analyze_screen":
        pass  # ha gia il suo print interno
    elif action == "list_processes":
        pass  # ha gia il suo print interno
    elif action == "kill_process":
        killed = res.get("killed", [])
        if killed: print(f"    Terminato: {', '.join(killed)}")
        else: print("   Nessun processo trovato")
    elif action == "get_temps":
        pass  # ha gia il suo print interno
    elif action in ("set_memory","get_memory","clear_memory",
                    "set_alarm","list_alarms","delete_alarm","set_ringtone"):
        pass  # hanno già i loro print interni
    else:
        result_str = res.get("result", "") if isinstance(res, dict) else str(res)
        print(f"   {result_str}" if result_str else "   Completato")
    print()

# ===================================================
# ACTION EXECUTOR
# ===================================================

class ActionExecutor:
    def __init__(self, workspace: Path, llm=None):
        self.workspace = ensure_workspace(workspace)
        self.actions = load_plugins(llm=llm)
        self.actions["run_command"]    = _run_command
        self.actions["get_system_info"] = _get_system_info
        self.actions["compile_project"] = _compile_project

    def execute(self, action_name: str, args: Dict[str, Any], confirm: bool = True) -> Dict[str, Any]:
        if action_name not in ALLOWED_ACTIONS:
            return {"status": "error", "reason": f"Azione non consentita: {action_name}"}
        if action_name not in self.actions:
            return {"status": "error", "reason": f"Azione non implementata: {action_name}"}

        if confirm and action_name in {"create_file", "write_file", "create_folder",
                                        "delete_file", "delete_folder", "run_command"}:
            print(f" Proposta: {action_name} → {args}")
            ok = input("Confermi? [y/N]: ").strip().lower()
            if ok != "y":
                return {"status": "cancelled"}

        try:
            res = self.actions[action_name](args, self.workspace, safe_resolve)
            return {"status": "ok", "result": res}
        except Exception as e:
            print(f"  Errore: {e}")
            traceback.print_exc()
            return {"status": "error", "reason": str(e)}


# ===================================================
# MAIN
# ===================================================


def _print_help():
    print("""
  ┌─────────────────────────────────────────────────────────┐
  │  PyLine — command reference                             │
  └─────────────────────────────────────────────────────────┘

  FILES & FOLDERS
    create file desktop/note.txt with content hello
    write file desktop/note.txt  → overwrite content
    rename desktop/note.txt to log.txt
    delete file desktop/note.txt
    delete folder desktop/myfolder
    copy / move  file src to dst
    search files for "report"
    fix file desktop/script.py  → AI fixes bugs

  OPEN
    open spotify / chrome / vscode / discord ...
    open url https://github.com
    open folder downloads
    analyze url https://example.com  → safety check

  OFFICE DOCUMENTS
    create word document desktop/doc.docx
    create excel file desktop/table.xlsx
    create powerpoint presentation desktop/slides.pptx
    create pdf desktop/report.pdf

  AI PROJECT GENERATION
    generate a python snake game
    generate a C++ calculator
    generate a website for a portfolio

  SYSTEM
    screenshot
    brightness 70
    list processes / top 10 by cpu
    kill process chrome.exe
    temperatures
    system info
    clean system  → removes temp files, reports heavy apps

  MEMORY & ALARMS
    remember that my name is Raffa
    show memory
    clear memory
    set alarm at 15:30 for drink water
    list alarms
    delete alarm drink water

  VOICE
    enable voice female ita / female eng / male eng
    disable voice
    voice status

  OTHER
    help  → show this message
    exit  → quit PyLine
""")

def main():
    parser = argparse.ArgumentParser(prog="pyline")
    parser.add_argument("--workspace", "-w", default=str(DEFAULT_WORKSPACE))
    parser.add_argument("--no-confirm", action="store_true")
    args = parser.parse_args()

    print("=" * 50)
    print("   PyLine — Assistente AI per il tuo PC")
    print("=" * 50)

    gpus = detect_gpus()
    device = select_device(gpus)
    llm = load_model(device)

    workspace = Path(args.workspace)
    ensure_workspace(workspace)
    executor = ActionExecutor(workspace, llm=llm)

    history = []
    print(" Digita un comando o una domanda. Scrivi 'exit' per uscire.\n")

    while True:
        try:
            txt = input("pyline> ").strip()
        except EOFError:
            break

        if not txt:
            continue
        if txt.lower() in {"exit", "quit", "esci"}:
            print(" Uscita da PyLine.")
            break

        if txt.lower() in {"help", "aiuto", "comandi", "?"}:
            _print_help()
            continue

        # Resetta timer idle monitor
        try:
            from plugins.command_sys import ping_activity; ping_activity()
        except Exception:
            pass

        parsed = preparse_command(txt)
        if parsed:
            out = executor.execute(parsed["action"], parsed.get("args", {}), confirm=not args.no_confirm)
            pretty_print(parsed["action"], out)
            continue

        parsed = ai_parse(llm, txt, history)

        if parsed is None:
            history.append({"role": "user", "content": txt})
            history.append({"role": "assistant", "content": "(risposta libera)"})

        elif isinstance(parsed, list):
            history.append({"role": "user", "content": txt})
            print(f" Esecuzione {len(parsed)} azioni...")
            for i, step in enumerate(parsed, 1):
                action = step.get("action")
                action_args = step.get("args", {})
                if action and action != "null":
                    print(f"  [{i}/{len(parsed)}] {action}")
                    out = executor.execute(action, action_args, confirm=not args.no_confirm)
                    pretty_print(action, out)
            history.append({"role": "assistant", "content": json.dumps(parsed)})

        else:
            action = parsed.get("action")
            action_args = parsed.get("args", {})
            if action and action != "null":
                history.append({"role": "user", "content": txt})
                out = executor.execute(action, action_args, confirm=not args.no_confirm)
                history.append({"role": "assistant", "content": json.dumps(parsed)})
                pretty_print(action, out)
            else:
                print("  Comando non riconosciuto.\n")

        if len(history) > 20:
            history = history[-20:]


if __name__ == "__main__":
    main()