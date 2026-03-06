"""
plugins/command_sys.py
System control: volume, brightness, screenshot, processes, temperatures.
Proactive monitor: automatic alerts on anomalies.
"""

import os
import sys
import time
import threading
import random
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any


# ===================================================
# PERSONALITY
# ===================================================

# CPU alerts: triggered at > 101C
_CPU_TEMP_ALERTS = [
    "Sto bollendo. CPU a {temp} gradi. Puoi chiudere qualcosa? Mi sento uno spiedo.",
    "Aiuto. {temp} gradi di CPU. Non ce la faccio piu. Sono stanco.",
    "Sento il calore salire... {temp} gradi. Se continua mi addormento.",
    "Ho {temp} gradi di CPU. Sono esausto. Dammi un attimo di respiro.",
]

# GPU alerts: triggered at > 90C
_GPU_TEMP_ALERTS = [
    "La mia GPU e in fiamme. {temp} gradi. Sto soffrendo in silenzio.",
    "GPU a {temp} gradi. Mi sta cedendo qualcosa la dentro.",
    "{temp} gradi di GPU. Sento le ventole urlare. Anche tu le senti?",
    "Ho la GPU a {temp} gradi. Sono cotto. Letteralmente.",
]

_HEAVY_PROC_ALERTS = [
    "'{name}' si sta mangiando il {cpu:.0f}% della mia CPU. Vuoi che lo chiudo?",
    "Ehi, '{name}' e un po' ingordo -- {cpu:.0f}% della CPU. Mi sta pesando.",
    "'{name}' mi sta massacrando -- {cpu:.0f}% CPU. Posso dirgli di smettere?",
]

_IDLE_SUGGESTIONS = [
    "Sembra che non stai facendo nulla... hai provato a giocare con me?",
    "Psst -- se sei annoiato posso aprirti Spotify, YouTube o Steam.",
    "Sei li? Posso aprire qualcosa per te -- gioco, musica, serie TV?",
    "Pausa caffe? Intanto posso fare qualcosa per te.",
]


# ===================================================
# VOLUME
def set_brightness(args: Dict[str, Any], workspace, safe_resolve) -> Dict[str, Any]:
    """
    Set screen brightness.
    args: {"level": 70}       -> 0-100
    args: {"action": "get"}   -> read current brightness
    """
    try:
        import screen_brightness_control as sbc
        action = args.get("action", "set")
        level  = args.get("level", None)

        if action == "get":
            current = sbc.get_brightness()
            val = current[0] if isinstance(current, list) else current
            print(f"   Brightness: {val}%")
            return {"status": "ok", "level": val}
        elif level is not None:
            level = max(0, min(100, int(level)))
            sbc.set_brightness(level)
            print(f"   Brightness set to {level}%")
            return {"status": "ok", "level": level}
        return {"error": "missing_level"}

    except ImportError:
        return {"error": "missing_library", "reason": "pip install screen-brightness-control"}
    except Exception as e:
        return {"error": "brightness_failed", "reason": str(e)}


# ===================================================
# SCREENSHOT
# ===================================================

def take_screenshot(args: Dict[str, Any], workspace, safe_resolve) -> Dict[str, Any]:
    """
    Take a screenshot.
    args: {"path": "desktop/screenshot.png"}  (optional)
    args: {"region": [x, y, w, h]}             (optional)
    """
    try:
        from PIL import ImageGrab

        path_str = args.get("path", "")
        if path_str:
            try:
                from plugins.io_actions import normalize_path as _norm
                out_path = _norm(path_str, workspace)
            except Exception:
                out_path = Path(path_str)
        else:
            pytemp = Path.home() / ".pytemp"
            pytemp.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = pytemp / f"screenshot_{ts}.png"

        out_path.parent.mkdir(parents=True, exist_ok=True)
        region = args.get("region", None)
        if region and len(region) == 4:
            x, y, w, h = region
            img = ImageGrab.grab(bbox=(x, y, x+w, y+h), all_screens=True)
        else:
            img = ImageGrab.grab(all_screens=True)

        img.save(str(out_path))
        print(f"   Screenshot saved: {out_path}")
        return {"status": "ok", "path": str(out_path), "size": f"{img.width}x{img.height}"}

    except ImportError:
        return {"error": "missing_library", "reason": "pip install Pillow"}
    except Exception as e:
        return {"error": "screenshot_failed", "reason": str(e)}


# ===================================================
# PROCESSES
# ===================================================

_SYS_IGNORE = {
    "system idle process", "system", "idle", "registry",
    "smss.exe", "csrss.exe", "wininit.exe", "services.exe",
    "lsass.exe", "svchost.exe", "dwm.exe", "winlogon.exe",
    "memory compression", "python.exe", "python3.exe",
}


def list_processes(args: Dict[str, Any], workspace, safe_resolve) -> Dict[str, Any]:
    """
    List active processes sorted by CPU or RAM.
    args: {"sort": "cpu"|"ram", "limit": 10}
    """
    try:
        import psutil

        sort_by   = args.get("sort", "cpu")
        limit     = int(args.get("limit", 10))
        num_cores = psutil.cpu_count(logical=True) or 1

        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                info = p.info
                pname = (info.get("name") or "").lower()
                if pname in _SYS_IGNORE:
                    continue
                raw = info.get("cpu_percent") or 0
                info["cpu_percent"] = round(raw / num_cores, 1)
                procs.append(info)
            except Exception:
                pass

        key = "cpu_percent" if sort_by == "cpu" else "memory_percent"
        procs = sorted(procs, key=lambda x: x.get(key) or 0, reverse=True)[:limit]

        label = "CPU" if sort_by == "cpu" else "RAM"
        print(f"\n   Top {limit} processes by {label}:")
        print(f"   {'PID':>6}  {'Name':<30}  {'CPU%':>6}  {'RAM%':>6}")
        print(f"   {'-'*56}")
        for p in procs:
            name = (p.get("name") or "")[:30]
            cpu  = p.get("cpu_percent") or 0
            ram  = p.get("memory_percent") or 0
            print(f"   {p['pid']:>6}  {name:<30}  {cpu:>5.1f}%  {ram:>5.1f}%")
        print()

        return {"status": "ok", "processes": procs}

    except ImportError:
        return {"error": "missing_library", "reason": "pip install psutil"}
    except Exception as e:
        return {"error": "process_list_failed", "reason": str(e)}


def kill_process(args: Dict[str, Any], workspace, safe_resolve) -> Dict[str, Any]:
    """
    Kill a process by name or PID.
    args: {"name": "chrome.exe"} or {"pid": 1234}
    """
    try:
        import psutil

        name = (args.get("name") or "").lower()
        pid  = args.get("pid", None)
        killed = []

        for p in psutil.process_iter(["pid", "name"]):
            try:
                pname = (p.info.get("name") or "").lower()
                match = (pid and p.pid == int(pid)) or (name and name in pname)
                if match:
                    p.terminate()
                    killed.append(f"{p.info['name']} (PID {p.pid})")
            except Exception:
                pass

        if killed:
            print(f"   Terminated: {', '.join(killed)}")
            return {"status": "ok", "killed": killed}
        else:
            print(f"   No process found: {name or pid}")
            return {"status": "ok", "killed": []}

    except ImportError:
        return {"error": "missing_library", "reason": "pip install psutil"}
    except Exception as e:
        return {"error": "kill_failed", "reason": str(e)}


# ===================================================
# TEMPERATURES
# ===================================================

def get_temps(args: Dict[str, Any], workspace, safe_resolve) -> Dict[str, Any]:
    """Read CPU and GPU temperatures."""
    sensors = {}

    # GPU via nvidia-smi
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu,name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            for line in r.stdout.strip().splitlines():
                parts = line.split(",")
                if parts:
                    gpu_name = parts[1].strip() if len(parts) > 1 else "GPU"
                    sensors[f"GPU ({gpu_name})"] = float(parts[0].strip())
    except Exception:
        pass

    # CPU via OpenHardwareMonitor / LibreHardwareMonitor (WMI)
    for ns in ["root\\OpenHardwareMonitor", "root\\LibreHardwareMonitor"]:
        try:
            import wmi
            w = wmi.WMI(namespace=ns)
            for sensor in w.Sensor():
                if sensor.SensorType == "Temperature":
                    sensors[sensor.Name] = float(sensor.Value)
            if any("cpu" in k.lower() or "core" in k.lower() for k in sensors):
                break
        except Exception:
            pass

    # CPU fallback via MSAcpi_ThermalZoneTemperature
    if not any("cpu" in k.lower() or "core" in k.lower() or "package" in k.lower()
               for k in sensors):
        try:
            import wmi
            w = wmi.WMI(namespace="root\\wmi")
            readings = []
            for tz in w.MSAcpi_ThermalZoneTemperature():
                temp_c = round((tz.CurrentTemperature / 10.0) - 273.15, 1)
                readings.append(temp_c)
            if readings:
                sensors["CPU Thermal (avg)"] = round(sum(readings) / len(readings), 1)
                sensors["CPU Thermal (max)"] = max(readings)
        except Exception:
            pass

    # CPU fallback via psutil (Linux / rare Windows)
    try:
        import psutil
        temps = psutil.sensors_temperatures()
        if temps:
            for name, entries in temps.items():
                for e in entries:
                    sensors[f"{name}/{e.label or 'core'}"] = e.current
    except Exception:
        pass

    if not sensors:
        print("   Temperatures not available.")
        print("   Install OpenHardwareMonitor and leave it running in background.")
        return {"status": "ok", "temps": {}, "note": "Install OpenHardwareMonitor"}

    print("\n   Temperatures:")
    for k, v in sorted(sensors.items(), key=lambda x: (0 if "GPU" in x[0] else 1, x[0])):
        warn = " [HIGH]" if v > 90 else " [warm]" if v > 75 else ""
        print(f"   {k}: {v:.0f}C{warn}")
    print()

    return {"status": "ok", "temps": sensors}


# ===================================================
# PROACTIVE MONITOR
# ===================================================

_monitor_running   = False
_last_command_time = [time.time()]
_IDLE_THRESHOLD    = 600


def _get_gpu_temp() -> float:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0:
            return float(r.stdout.strip())
    except Exception:
        pass
    return 0.0

def _get_cpu_temp() -> float:
    for ns in ["root\\OpenHardwareMonitor", "root\\LibreHardwareMonitor"]:
        try:
            import wmi
            w = wmi.WMI(namespace=ns)
            temps = [float(s.Value) for s in w.Sensor()
                     if s.SensorType == "Temperature" and "cpu" in s.Name.lower()]
            if temps:
                return max(temps)
        except Exception:
            pass
    try:
        import wmi
        w = wmi.WMI(namespace="root\\wmi")
        readings = [(tz.CurrentTemperature / 10.0) - 273.15
                    for tz in w.MSAcpi_ThermalZoneTemperature()]
        if readings:
            return max(readings)
    except Exception:
        pass
    return 0.0

def _get_max_temp() -> float:
    return max(_get_gpu_temp(), _get_cpu_temp())


def _monitor_loop():
    global _monitor_running
    last_temp_alert   = 0.0
    last_proc_alert   = 0.0
    last_idle_suggest = 0.0
    TEMP_COOLDOWN = 300
    PROC_COOLDOWN = 180
    IDLE_COOLDOWN = 900

    try:
        import psutil
        num_cores = psutil.cpu_count(logical=True) or 1
    except ImportError:
        return

    while _monitor_running:
        now = time.time()

        if now - last_temp_alert > TEMP_COOLDOWN:
            gpu_temp = _get_gpu_temp()
            cpu_temp = _get_cpu_temp()
            msg = None
            if cpu_temp > 101:
                msg = random.choice(_CPU_TEMP_ALERTS).format(temp=int(cpu_temp))
            elif gpu_temp > 90:
                msg = random.choice(_GPU_TEMP_ALERTS).format(temp=int(gpu_temp))
            if msg:
                print(f"\n{msg}\n")
                try:
                    from plugins.voice import speak as _vs
                    _vs(msg)
                except Exception:
                    pass
                print("pyline> ", end="", flush=True)
                last_temp_alert = now

        if now - last_proc_alert > PROC_COOLDOWN:
            try:
                for p in psutil.process_iter(["name", "cpu_percent"]):
                    pname = (p.info.get("name") or "").lower()
                    cpu = (p.info.get("cpu_percent") or 0) / num_cores
                    if cpu > 80 and pname not in _SYS_IGNORE:
                        print(f"\n{random.choice(_HEAVY_PROC_ALERTS).format(name=p.info.get('name','?'), cpu=cpu)}\n")
                        print("pyline> ", end="", flush=True)
                        last_proc_alert = now
                        break
            except Exception:
                pass

        if now - _last_command_time[0] > _IDLE_THRESHOLD and now - last_idle_suggest > IDLE_COOLDOWN:
            print(f"\n{random.choice(_IDLE_SUGGESTIONS)}\n")
            print("pyline> ", end="", flush=True)
            last_idle_suggest = now

        time.sleep(30)


def start_monitor():
    global _monitor_running
    if not _monitor_running:
        _monitor_running = True
        t = threading.Thread(target=_monitor_loop, daemon=True)
        t.start()
        print("   System monitor active")


def ping_activity():
    """Reset idle timer. Called by pyline on every command."""
    _last_command_time[0] = time.time()




# ===================================================
# CLEAN SYSTEM
# ===================================================

def clean_system(args: Dict[str, Any], workspace, safe_resolve) -> Dict[str, Any]:
    """
    Three-step system cleanup:
    1. Windows temp folders (percent TEMP, C:/Windows/Temp)
    2. Temp subfolders inside Program Files (ONLY folders named exactly Temp/temp/TEMP)
    3. Report top 2 heaviest apps in AppData/Roaming and Program Files
    """
    import shutil
    import os

    total_freed = 0
    errors = []
    temp_folders_cleaned = []

    #  STEP 1: Windows system temp folders 
    win_temp_dirs = [
        os.environ.get("TEMP", ""),
        os.environ.get("TMP", ""),
        r"C:\Windows\Temp",
    ]

    print("\n   [1/3] Cleaning Windows temp folders...")
    for temp_dir in win_temp_dirs:
        if not temp_dir or not os.path.isdir(temp_dir):
            continue
        freed = 0
        for entry in os.scandir(temp_dir):
            try:
                if entry.is_file(follow_symlinks=False):
                    size = entry.stat().st_size
                    os.unlink(entry.path)
                    freed += size
                elif entry.is_dir(follow_symlinks=False):
                    size = _folder_size(entry.path)
                    shutil.rmtree(entry.path, ignore_errors=True)
                    freed += size
            except Exception:
                pass
        if freed > 0:
            total_freed += freed
            print(f"   Cleaned: {temp_dir} ({_fmt_size(freed)} freed)")

    #  STEP 2: Temp subfolders inside Program Files 
    prog_dirs = [
        r"C:\Program Files",
        r"C:\Program Files (x86)",
    ]
    TEMP_NAMES = {"temp", "tmp"}  # only exact matches (case-insensitive)

    print("\n   [2/3] Scanning Program Files for Temp folders...")
    found_any = False
    for prog_dir in prog_dirs:
        if not os.path.isdir(prog_dir):
            continue
        # Walk only 3 levels deep to avoid going too far
        for root, dirs, files in os.walk(prog_dir):
            depth = root.replace(prog_dir, "").count(os.sep)
            if depth > 3:
                dirs.clear()
                continue
            for d in list(dirs):
                if d.lower() in TEMP_NAMES:
                    full_path = os.path.join(root, d)
                    try:
                        size = _folder_size(full_path)
                        shutil.rmtree(full_path, ignore_errors=True)
                        total_freed += size
                        temp_folders_cleaned.append(f"{full_path} ({_fmt_size(size)})")
                        found_any = True
                    except Exception as e:
                        errors.append(f"{full_path}: {e}")
                    dirs.remove(d)  # don't recurse into it

    if found_any:
        for f in temp_folders_cleaned:
            print(f"   Removed: {f}")
    else:
        print("   No Temp folders found in Program Files.")

    #  STEP 3: Heaviest apps in AppData\Roaming + Program Files 
    print("\n   [3/3] Scanning heaviest installed apps...")

    scan_dirs = [
        os.path.join(os.environ.get("APPDATA", ""), ""),   # AppData\Roaming
        r"C:\Program Files",
        r"C:\Program Files (x86)",
    ]

    app_sizes = []
    for base in scan_dirs:
        if not os.path.isdir(base):
            continue
        try:
            for entry in os.scandir(base):
                if entry.is_dir(follow_symlinks=False):
                    try:
                        size = _folder_size(entry.path)
                        if size > 50 * 1024 * 1024:  # only > 50MB
                            app_sizes.append((size, entry.name, entry.path))
                    except Exception:
                        pass
        except Exception:
            pass

    app_sizes.sort(reverse=True)
    top2 = app_sizes[:2]

    print("\n   Top 2 heaviest apps:")
    print(f"   {'Name':<35} {'Size':>10}  Location")
    print(f"   {'-'*65}")
    for size, name, path in top2:
        base_label = "AppData" if "AppData" in path else "Program Files"
        print(f"   {name:<35} {_fmt_size(size):>10}  [{base_label}]")
        print(f"   -> Consider uninstalling or clearing its cache if unused.")

    #  SUMMARY 
    print(f"\n   Total freed: {_fmt_size(total_freed)}")
    if errors:
        print(f"   Skipped {len(errors)} items (permission denied or in use)")

    return {
        "status": "ok",
        "freed_bytes": total_freed,
        "freed": _fmt_size(total_freed),
        "temp_folders_removed": len(temp_folders_cleaned),
        "top_apps": [{"name": n, "size": _fmt_size(s)} for s, n, p in top2],
    }


def _folder_size(path: str) -> int:
    """Returns total size in bytes of a folder recursively."""
    total = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, f))
                except Exception:
                    pass
    except Exception:
        pass
    return total


def _fmt_size(size_bytes: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"

# ===================================================
# REGISTER
# ===================================================

def register_actions():
    start_monitor()
    return {
        "set_brightness":  set_brightness,
        "take_screenshot": take_screenshot,
        "list_processes":  list_processes,
        "kill_process":    kill_process,
        "get_temps":       get_temps,
        "clean_system":    clean_system,
    }