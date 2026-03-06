"""
plugins/open_actions.py
Apre app, URL, directory.
Novità: analisi URL prima dell'apertura per rilevare link pericolosi.
"""

import os
import sys
import subprocess
import webbrowser
import ctypes
import ctypes.wintypes
import re
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, Any


# ===================================================
# UTILITY
# ===================================================

def get_real_desktop() -> Path:
    """Rileva il vero percorso Desktop, anche se è in OneDrive."""
    try:
        buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf)
        p = Path(buf.value)
        if p.exists():
            return p
    except Exception:
        pass
    p1 = Path.home() / "OneDrive" / "Desktop"
    p2 = Path.home() / "Desktop"
    return p1 if p1.exists() else p2


def normalize_path(path_str: str) -> Path:
    path_str = path_str.replace("USERNAME", os.getenv("USERNAME") or "")
    path_str = os.path.expandvars(path_str)
    path_str = os.path.expanduser(path_str)
    return Path(path_str).resolve()


# ===================================================
# URL ANALYZER
# ===================================================

# Estensioni che scaricano/eseguono qualcosa automaticamente
_DANGEROUS_EXTENSIONS = {
    ".exe", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".jar",
    ".scr", ".com", ".pif", ".reg", ".hta", ".wsf", ".lnk"
}

# Domini noti per phishing/malware (lista base, espandibile)
_SUSPICIOUS_PATTERNS = [
    r"bit\.ly", r"tinyurl\.com", r"t\.co",           # shortener (non pericolosi ma da verificare)
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",           # IP diretto invece di dominio
    r"[a-z0-9\-]+\.tk$", r"[a-z0-9\-]+\.ml$",        # TLD gratis spesso usati per phishing
    r"[a-z0-9\-]+\.ga$", r"[a-z0-9\-]+\.cf$",
    r"free.*download", r"crack.*download",
    r"download.*free", r"keygen",
    r"@",                                              # URL con @ sono quasi sempre phishing
]


def analyze_url(url: str) -> dict:
    """
    Analizza un URL e ritorna un report con:
    - dominio
    - protocollo
    - path
    - estensione finale (se c'è un file)
    - warnings: lista di avvisi
    - risk: "safe" | "suspicious" | "dangerous"
    """
    warnings = []
    risk = "safe"

    # Aggiunge schema se mancante
    if not url.startswith(("http://", "https://", "ftp://", "ms-settings:")):
        url = "https://" + url

    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        path = parsed.path
        scheme = parsed.scheme
    except Exception:
        return {"risk": "unknown", "warnings": ["URL non analizzabile"], "url": url}

    # Controlla HTTPS
    if scheme == "http":
        warnings.append("⚠️  Usa HTTP (non cifrato) — i tuoi dati non sono protetti")
        risk = "suspicious"

    # Controlla .onion — dark web, sempre sospetto
    if domain.endswith(".onion"):
        warnings.append("🚨 Sito .onion — appartiene al dark web, accessibile solo via Tor")
        risk = "dangerous"

    # TLD ad alto rischio
    HIGH_RISK_TLDS = [".ru", ".cn", ".tk", ".ml", ".ga", ".cf", ".gq", ".pw", ".top", ".xyz"]
    for tld in HIGH_RISK_TLDS:
        if domain.endswith(tld):
            warnings.append(f"⚠️  TLD '{tld}' spesso associato a siti pericolosi o spam")
            if risk == "safe":
                risk = "suspicious"
            break

    # Controlla estensione finale del path
    ext = Path(path).suffix.lower() if path else ""
    if ext in _DANGEROUS_EXTENSIONS:
        warnings.append(f"🚨 L'URL punta a un file {ext.upper()} che potrebbe eseguire codice!")
        risk = "dangerous"

    # Controlla pattern sospetti nel dominio + path
    full = domain + path
    for pattern in _SUSPICIOUS_PATTERNS:
        if re.search(pattern, full, re.IGNORECASE):
            if pattern == r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}":
                warnings.append("⚠️  URL usa un indirizzo IP diretto — nessun dominio verificabile")
            elif pattern == r"@":
                warnings.append("🚨 URL contiene '@' — classico trucco di phishing!")
                risk = "dangerous"
            elif "shortener" in pattern or "bit.ly" in pattern:
                warnings.append("⚠️  URL abbreviato — non si vede la destinazione reale")
            else:
                warnings.append(f"⚠️  Pattern sospetto rilevato nell'URL: {pattern}")
            if risk != "dangerous":
                risk = "suspicious"

    # Nessun avviso
    if not warnings:
        warnings.append("✅ Nessun rischio rilevato")

    return {
        "url": url,
        "domain": domain,
        "scheme": scheme,
        "path": path,
        "file_ext": ext or "nessuna",
        "risk": risk,
        "warnings": warnings,
    }


# ===================================================
# OPEN APP
# ===================================================

def open_app(args: Dict[str, Any], workspace, safe_resolve) -> Dict[str, Any]:
    """Apre un'applicazione — mapping diretto + ricerca su disco."""
    app = (args.get("app") or args.get("app_name") or "").strip().lower()
    if not app:
        return {"error": "missing_app"}

    desktop = get_real_desktop()

    # Mapping diretto app comuni
    mapping = {
        "paint": "mspaint.exe",
        "notepad": "notepad.exe",
        "blocco note": "notepad.exe",
        "bloc notes": "notepad.exe",
        "explorer": "explorer.exe",
        "esplora file": "explorer.exe",
        "file manager": "explorer.exe",
        "cmd": "cmd.exe",
        "prompt dei comandi": "cmd.exe",
        "terminal": "wt.exe",
        "windows terminal": "wt.exe",
        "powershell": "powershell.exe",
        "impostazioni": "ms-settings:",
        "edge": "msedge.exe",
        "microsoft edge": "msedge.exe",
        "chrome": "chrome.exe",
        "google chrome": "chrome.exe",
        "firefox": "firefox.exe",
        "opera": "opera.exe",
        "brave": "brave.exe",
        "discord": "discord.exe",
        "spotify": "spotify.exe",
        "steam": "steam.exe",
        "vscode": "code.exe",
        "visual studio code": "code.exe",
        "code": "code.exe",
        "taskmgr": "taskmgr.exe",
        "task manager": "taskmgr.exe",
        "gestore attività": "taskmgr.exe",
        "calc": "calc.exe",
        "calcolatrice": "calc.exe",
        "snip": "snippingtool.exe",
        "cattura": "snippingtool.exe",
        "vlc": "vlc.exe",
        "winrar": "winrar.exe",
        "7zip": "7zfm.exe",
        "obs": "obs64.exe",
        "telegram": "telegram.exe",
        "whatsapp": "whatsapp.exe",
        "slack": "slack.exe",
        "zoom": "zoom.exe",
        "teams": "teams.exe",
        "word": "winword.exe",
        "excel": "excel.exe",
        "powerpoint": "powerpnt.exe",
    }

    exe = mapping.get(app)
    if exe:
        try:
            os.startfile(exe)
            return {"status": "ok", "result": f"Aperto: {app}"}
        except Exception as e:
            pass  # Prova ricerca su disco

    # Ricerca su disco
    search_paths = [
        desktop,
        Path(os.getenv("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.getenv("ProgramData", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
        Path(os.getenv("LOCALAPPDATA", "")) / "Programs",
    ]

    candidates = []
    for base in search_paths:
        if not base.exists():
            continue
        try:
            for ext in ("*.lnk", "*.exe"):
                for path in base.rglob(ext):
                    if app in path.stem.lower():
                        candidates.append(path)
        except Exception:
            continue

    if candidates:
        best = sorted(
            candidates,
            key=lambda p: (app == p.stem.lower(), p.stat().st_mtime),
            reverse=True
        )[0]
        try:
            os.startfile(best)
            return {"status": "ok", "result": f"Aperto: {app}", "path": str(best)}
        except Exception as e:
            return {"error": "open_failed", "reason": str(e)}

    # Fallback shell
    try:
        subprocess.Popen(app, shell=True)
        return {"status": "ok", "result": f"Aperto: {app} (shell)"}
    except Exception as e:
        return {"error": "not_found", "app": app, "reason": str(e)}


# ===================================================
# OPEN URL (con analisi preventiva)
# ===================================================

def open_url(args: Dict[str, Any], workspace, safe_resolve) -> Dict[str, Any]:
    """
    Analizza l'URL prima di aprirlo.
    - Se safe → apre direttamente
    - Se suspicious → mostra avvisi e chiede conferma
    - Se dangerous → blocca e mostra avvisi (chiede conferma esplicita)
    """
    url = args.get("url") or args.get("link") or ""
    if not url:
        return {"error": "missing_url"}

    # Analisi
    report = analyze_url(url)
    url = report["url"]  # URL normalizzato con schema

    print(f"\n🔍 Analisi URL: {url}")
    print(f"   Dominio  : {report['domain']}")
    print(f"   Protocollo: {report['scheme'].upper()}")
    print(f"   File/ext : {report['file_ext']}")
    print(f"   Rischio  : {report['risk'].upper()}")
    for w in report["warnings"]:
        print(f"   {w}")

    if report["risk"] == "safe":
        webbrowser.open(url)
        return {"status": "ok", "result": f"Aperto: {url}", "analysis": report}

    elif report["risk"] == "suspicious":
        print("\n❓ L'URL ha qualche avviso. Vuoi aprirlo comunque? [y/N]: ", end="")
        choice = input().strip().lower()
        if choice == "y":
            webbrowser.open(url)
            return {"status": "ok", "result": f"Aperto con avvisi: {url}", "analysis": report}
        else:
            return {"status": "cancelled", "reason": "Utente ha rifiutato apertura URL sospetto", "analysis": report}

    else:  # dangerous
        print("\n🚨 URL PERICOLOSO — apertura bloccata.")
        print("   Sei SICURO di voler aprire questo URL? Digita 'APRI' per confermare: ", end="")
        choice = input().strip()
        if choice == "APRI":
            webbrowser.open(url)
            return {"status": "ok", "result": f"Aperto (forzato): {url}", "analysis": report}
        else:
            return {"status": "blocked", "reason": "URL pericoloso bloccato", "analysis": report}


def analyze_url_only(args: Dict[str, Any], workspace, safe_resolve) -> Dict[str, Any]:
    """Analizza un URL senza aprirlo."""
    url = args.get("url") or args.get("link") or ""
    if not url:
        return {"error": "missing_url"}
    report = analyze_url(url)
    print(f"\n🔍 Analisi URL: {report['url']}")
    print(f"   Dominio   : {report['domain']}")
    print(f"   Protocollo: {report['scheme'].upper()}")
    print(f"   File/ext  : {report['file_ext']}")
    print(f"   Rischio   : {report['risk'].upper()}")
    for w in report["warnings"]:
        print(f"   {w}")
    return {"status": "ok", "analysis": report}


# ===================================================
# OPEN DIR
# ===================================================

def open_dir(args: Dict[str, Any], workspace=None, safe_resolve=None) -> Dict[str, Any]:
    path = args.get("path")
    if not path:
        return {"error": "missing_path"}

    try:
        username = os.getlogin()
    except Exception:
        username = os.getenv("USERNAME", "")
    path = path.replace("<USERNAME>", username)

    if "Desktop" in path or "desktop" in path:
        for p in [
            Path.home() / "OneDrive" / "Desktop",
            Path.home() / "Desktop",
        ]:
            if p.exists():
                path = str(p)
                break

    if "<VERSION>" in path:
        version = f"{sys.version_info.major}{sys.version_info.minor}"
        path = path.replace("<VERSION>", version)

    p = Path(path).expanduser().resolve()
    if not p.exists():
        return {"error": "not_found", "path": str(p)}

    try:
        if sys.platform.startswith("win"):
            os.startfile(p)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(p)])
        else:
            subprocess.run(["xdg-open", str(p)])
        return {"status": "ok", "result": f"Aperta: {p}"}
    except Exception as e:
        return {"error": "open_failed", "reason": str(e)}


# ===================================================
# REGISTER
# ===================================================

def register_actions():
    return {
        "open_app": open_app,
        "open_url": open_url,
        "open_dir": open_dir,
        "analyze_url": analyze_url_only,
    }