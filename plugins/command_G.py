# command_G.py — Generazione progetti AI autonomi
# Riscritto per llama-cpp + Gemma 3 (riceve llm già caricato da pyline)

import os
import sys
import json
import subprocess
import traceback
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple

# ===================================================================
# UTILITY
# ===================================================================

def run_command(cmd: List[str], cwd: Path, timeout: int = 60) -> Tuple[bool, str]:
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        output = result.stdout.strip() or result.stderr.strip()
        return (result.returncode == 0, output)
    except subprocess.TimeoutExpired:
        return (False, f" Timeout ({timeout}s)")
    except FileNotFoundError:
        return (False, f" Comando non trovato: {cmd[0]}")
    except Exception as e:
        return (False, f" Errore: {str(e)}")


def detect_language(files: List[str]) -> str:
    count = {l: 0 for l in ["python", "javascript", "typescript", "html", "css", "java", "c", "cpp", "go", "rust", "kotlin", "swift", "ruby", "php", "csharp", "lua", "dart", "shell"]}
    ext_map = {
        ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "typescript",
        ".html": "html", ".htm": "html", ".css": "css", ".java": "java",
        ".c": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".go": "go", ".rs": "rust",
        ".kt": "kotlin", ".kts": "kotlin", ".swift": "swift",
        ".rb": "ruby", ".php": "php", ".cs": "csharp",
        ".lua": "lua", ".dart": "dart", ".sh": "shell", ".bash": "shell",
    }
    for f in files:
        ext = Path(f).suffix.lower()
        if ext in ext_map:
            count[ext_map[ext]] += 1

    # Linguaggi compilati hanno sempre priorità — anche con 1 solo file
    PRIORITY = ["c", "cpp", "rust", "go", "java", "csharp", "kotlin", "swift", "dart", "python"]
    for lang in PRIORITY:
        if count[lang] > 0:
            return lang

    best = max(count.items(), key=lambda x: x[1])
    return best[0] if best[1] > 0 else "unknown"


def detect_language_from_techs(techs: List[str]) -> str:
    for t in techs:
        t = t.lower()
        if "python" in t or t == "py": return "python"
        if "java" in t and "script" not in t: return "java"
        if "javascript" in t or t == "js": return "javascript"
        if "typescript" in t or t == "ts": return "typescript"
        if "html" in t or "web" in t or "css" in t: return "html"
        if "c++" in t or "cpp" in t: return "cpp"
        if t == "c": return "c"
        if "go" in t or "golang" in t: return "go"
        if "rust" in t: return "rust"
        if "kotlin" in t or t == "kt": return "kotlin"
        if "swift" in t: return "swift"
        if "ruby" in t or t == "rb": return "ruby"
        if "php" in t: return "php"
        if "csharp" in t or "c#" in t or ".net" in t: return "csharp"
        if "lua" in t: return "lua"
        if "dart" in t or "flutter" in t: return "dart"
        if "shell" in t or "bash" in t or "sh" in t: return "shell"
        if "sql" in t: return "sql"
        if "asm" in t or "assembly" in t: return "asm"
    return "unknown"


def get_language_guidelines(lang: str) -> str:
    guidelines = {
        "python":     "Create a Python project with main.py as entry point. If it's a game use pygame. Include requirements.txt.",
        "javascript": "Create vanilla JS project with index.html and js/script.js. Link CSS and JS correctly in HTML.",
        "typescript": "Create TypeScript project with src/index.ts and tsconfig.json.",
        "html":       (
            "Create a PROFESSIONAL static website with MANDATORY separate files: index.html, css/style.css, js/script.js. "
            "index.html MUST have: sticky navbar with logo + nav links (Home, Products, About, Contact) + hamburger button for mobile; "
            "hero section with big title, subtitle, call-to-action button; "
            "products/features section with at least 3 cards in CSS grid; "
            "about section; contact form (name, email, message, submit); footer with copyright. "
            "css/style.css MUST have: CSS variables for colors and fonts, Google Fonts @import, "
            "flexbox/grid layouts, hover effects with transitions, responsive media queries for mobile, "
            "styled buttons and cards with box-shadow. "
            "js/script.js MUST have: hamburger menu toggle, smooth scroll on nav links, "
            "form validation with error messages shown in DOM, scroll animation for cards (add class on scroll), "
            "active nav link highlight based on scroll position. "
            "NEVER put CSS or JS inside HTML file. Link them with <link> and <script> tags."
        ),
        "javascript": "Create vanilla JS project with index.html, css/style.css, js/script.js. Link CSS and JS correctly in HTML.",
        "c":          "Create C project with src/main.c only. NO CSS, NO JS, NO HTML files. Target Windows with MSYS2/gcc. Use windows.h instead of unistd.h. Use system('cls') not system('clear'). Use Sleep() not usleep(). For terminal games use conio.h for getch() and kbhit(). Only use standard C libraries available on Windows.",
        "cpp":        "Create C++ project with src/main.cpp only. NO CSS, NO JS, NO HTML files. Target Windows with MSYS2/g++. Use windows.h instead of unistd.h. Use system('cls') not system('clear'). Use Sleep() not usleep(). For terminal games use conio.h for getch() and kbhit(). Only use standard C++ libraries available on Windows.",
        "go":         "Create Go project with main.go and go.mod.",
        "rust":       "Create Rust project with src/main.rs and Cargo.toml.",
        "kotlin":     "Create Kotlin project with src/Main.kt as entry point.",
        "swift":      "Create Swift project with Sources/main.swift and Package.swift.",
        "ruby":       "Create Ruby project with main.rb as entry point. Include Gemfile.",
        "php":        "Create PHP project with index.php as entry point. Separate logic from HTML.",
        "csharp":     "Create C# project with Program.cs and a .csproj file.",
        "lua":        "Create Lua project with main.lua as entry point.",
        "dart":       "Create Dart project with bin/main.dart and pubspec.yaml.",
        "shell":      "Create a shell script project with main.sh as entry point. Make it executable.",
        "sql":        "Create SQL project with schema.sql for table definitions and queries.sql for queries.",
        "asm":        "Create assembly project with main.asm. Specify Intel syntax. Include build instructions.",
        "unknown":    "Create a well-structured project in the most appropriate language. Separate files logically.",
    }
    return guidelines.get(lang, guidelines["unknown"])


def _print_compile_instructions(target: Path, final_lang: str) -> Tuple[bool, str]:
    """Stampa i comandi per compilare manualmente nel terminale."""
    sources_c    = list(target.rglob("*.c"))
    sources_cpp  = list(target.rglob("*.cpp")) + list(target.rglob("*.cc"))
    sources_java = list(target.rglob("*.java"))
    exe = f"{target.name}.exe"

    print(f"\n{'='*55}")
    print(f" Per compilare '{target.name}' copia il comando nel terminale:\n")

    if final_lang == "c" and sources_c:
        src = ' '.join(f'"{s}"' for s in sources_c)
        print(f"   gcc   →  gcc {src} -o {exe} -lm")

    elif final_lang == "cpp" and sources_cpp:
        src = ' '.join(f'"{s}"' for s in sources_cpp)
        print(f"   g++   →  g++ {src} -o {exe}")
        print(f"   cl    →  cl {src} /Fe{exe}")

    elif final_lang == "java" and sources_java:
        src = ' '.join(f'"{s}"' for s in sources_java)
        print(f"   javac →  javac {src}")
        print(f"   run   →  java Main")

    elif final_lang == "csharp":
        print(f"   dotnet →  dotnet build && dotnet run")

    elif final_lang == "go":
        print(f"   go    →  go build ./...")
        print(f"   run   →  go run .")

    elif final_lang == "rust":
        print(f"   cargo →  cargo build && cargo run")

    print(f"\n Cartella: {target}")
    print(f"{'='*55}\n")
    return (True, "istruzioni stampate")


def build_and_run(lang: str, cwd: Path) -> Tuple[bool, str]:
    """Usato solo per Python, HTML, JS — esecuzione automatica senza chiedere."""
    try:
        if lang == "python":
            main = next(cwd.glob("**/main.py"), None)
            if main:
                return run_command([sys.executable, str(main)], cwd, timeout=15)
            return (False, "main.py non trovato")
        elif lang == "javascript":
            js = list(cwd.glob("**/*.js"))
            if js:
                return run_command(["node", js[0].name], cwd, timeout=10)
            return (False, "Nessun file JS trovato")
        elif lang in {"html", "css"}:
            html = list(cwd.rglob("*.html"))
            if html:
                return (True, f"Apri nel browser: {html[0]}")
            return (False, "Nessun file HTML trovato")
        return (False, "usa _interactive_compile per questo linguaggio")
    except Exception as e:
        return (False, str(e))


def ensure_support_files(target: Path, lang: str) -> None:
    try:
        if lang == "python" and not (target / "requirements.txt").exists():
            (target / "requirements.txt").write_text("# Dipendenze\n", encoding="utf-8")
        if lang in {"javascript", "typescript"} and not (target / "package.json").exists():
            pkg = {"name": target.name, "version": "1.0.0", "main": "index.js",
                   "scripts": {"start": "node index.js"}, "license": "MIT"}
            (target / "package.json").write_text(json.dumps(pkg, indent=2), encoding="utf-8")
    except Exception as e:
        print(f" Support files warning: {e}")


def _sanitize_filename(name: str) -> str:
    name = name.strip().replace(" ", "_")
    if name.startswith("./"):
        name = name[2:]
    return re.sub(r'[<>:"\\|?*]', "_", name)


def _is_valid_filename(line: str) -> bool:
    return bool(re.match(r'^[\w\-\./]+?\.[a-zA-Z0-9_]+$', line.strip()))


def clean_code_output(text: str, fname: str = "") -> str:
    text = re.sub(r"```[a-zA-Z0-9_+-]*", "", text)
    text = text.replace("```", "").replace("~~~", "").strip()
    # Rimuove separatori rimasti nel codice
    text = re.sub(r'\n@{2,}.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n§{2,}.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^@{2,}.*\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'^§{2,}.*\n?', '', text, flags=re.MULTILINE)

    ext = Path(fname).suffix.lower() if fname else ""

    # Linguaggi che NON usano import/from come prima riga — restituisci direttamente
    NO_SKIP_EXTS = {
        ".html", ".htm", ".css", ".js", ".ts", ".tsx",
        ".json", ".md", ".yaml", ".yml", ".toml", ".xml",
        ".sh", ".bat", ".ps1", ".makefile", ".mk",
        ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp",
        ".java", ".kt", ".go", ".rs", ".rb", ".php",
        ".swift", ".cs", ".lua", ".r", ".dart", ".zig",
        ".sql", ".graphql", ".proto",
    }
    if ext in NO_SKIP_EXTS:
        return text.strip()

    # Per Python e simili: salta righe inutili prima del codice vero
    lines = text.splitlines()
    cleaned = []
    skip = True
    PYTHON_STARTERS = ("import ", "from ", "#!", "def ", "class ", "if ", "for ", "while ", "try:", "with ", "@")
    for line in lines:
        s = line.strip()
        if any(s.startswith(st) for st in PYTHON_STARTERS):
            skip = False
        if skip:
            if s == "" or re.match(r"^[a-zA-Z\s]+$", s):
                continue
            else:
                skip = False
        cleaned.append(line)
    while cleaned and (cleaned[-1].strip() == "" or re.match(r"^[a-zA-Z\s]+$", cleaned[-1].strip())):
        cleaned.pop()
    return "\n".join(cleaned).strip()


def _extract_files_from_output(raw: str, prompt_sent: str) -> List[Tuple[str, str]]:
    out = raw
    if out.startswith(prompt_sent):
        out = out[len(prompt_sent):].strip()
    out = out.replace("\r\n", "\n")
    out = re.sub(r'(?m)^(?:- ){3,}.*$', '', out)

    parts = [p.strip() for p in out.split("@@@") if p.strip()]
    files: List[Tuple[str, str]] = []

    for part in parts:
        if part.strip() == "§§§":
            continue
        lines = part.splitlines()
        while lines and lines[0].strip() == "":
            lines.pop(0)
        if not lines:
            continue

        possible_fname = lines[0].strip()
        body_lines = lines[1:] if len(lines) > 1 else []

        if _is_valid_filename(possible_fname):
            fname = _sanitize_filename(possible_fname)
            body = clean_code_output("\n".join(body_lines), fname)
            if body:
                files.append((fname, body))
            continue

        m = re.search(r'([a-zA-Z0-9_\-./]{1,200}\.[a-zA-Z0-9_]{1,10})', part)
        if m:
            fname = _sanitize_filename(m.group(1))
            body = clean_code_output(part[part.find(m.group(1)) + len(m.group(1)):].strip(), fname)
            if body:
                files.append((fname, body))
            continue

        joined = "\n".join(lines).strip()
        bullets = sum(1 for l in lines if l.strip().startswith(("-", "•", "*")))
        if bullets > max(2, len(lines) // 4):
            continue
        body = clean_code_output(joined)
        if body:
            files.append((_sanitize_filename(possible_fname or "main.py"), body))

    return files




_llm_ref = None

def set_llm(llm) -> None:
    """Chiamato da pyline.py dopo aver caricato il modello."""
    global _llm_ref
    _llm_ref = llm


def _call_gemma(prompt: str, max_tokens: int = 4096) -> str:
    """Chiama Gemma via llama-cpp. Usa _llm_ref se disponibile, altrimenti carica da solo."""
    if _llm_ref is not None:
        llm = _llm_ref
    else:
        from llama_cpp import Llama
        gguf = list(Path("./models").rglob("*.gguf"))
        if not gguf:
            raise RuntimeError("Nessun modello GGUF trovato in ./models")
        llm = Llama(model_path=str(gguf[0]), n_ctx=4096, n_gpu_layers=-1, verbose=False)

    resp = llm.create_chat_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.0,
    )
    return resp["choices"][0]["message"]["content"].strip()


def detect_lang_from_user_text(text: str, techs: list) -> str:
    """
    Rileva il linguaggio dal testo dell'utente o dalla lista techs.
    Priorità: testo utente > techs list.
    """
    t = text.lower()
    # Ordine importante: prima i più specifici
    if "c++" in t or "cpp" in t:              return "cpp"
    if "c#" in t or "csharp" in t or ".net" in t: return "csharp"
    if re.search(r'\bc\b', t):                return "c"
    if "python" in t or " py " in t:          return "python"
    if "javascript" in t or " js " in t:      return "javascript"
    if "typescript" in t or " ts " in t:      return "typescript"
    if "html" in t or "sito web" in t or "website" in t or "web" in t: return "html"
    if "java" in t:                            return "java"
    if "rust" in t:                            return "rust"
    if "golang" in t or " go " in t:          return "go"
    if "kotlin" in t:                          return "kotlin"
    if "swift" in t:                           return "swift"
    if "ruby" in t:                            return "ruby"
    if "php" in t:                             return "php"
    if "lua" in t:                             return "lua"
    if "dart" in t or "flutter" in t:         return "dart"
    # Fallback su techs
    return detect_language_from_techs(techs)


def build_prompt_for_lang(lang: str, name: str, spec: str, techs: list) -> str:
    """Costruisce un prompt specifico e ottimizzato per ogni linguaggio."""
    tech_str = ", ".join(techs) if techs else lang

    PROMPTS = {
        "python": (
            f"You are an expert Python developer. Create a complete Python project.\n"
            f"PROJECT NAME: {name}\n"
            f"DESCRIPTION: {spec}\n"
            f"RULES:\n"
            f"- ONLY .py files and requirements.txt. ABSOLUTELY NO HTML, CSS, JS files.\n"
            f"- Entry point is always main.py\n"
            f"- If it's a game, use pygame. Include gravity, jump (SPACE), collision detection.\n"
            f"- Write complete, working code. No placeholders.\n"
            f"OUTPUT FORMAT: first line = relative path, then file content, then @@@. End with §§§.\n"
            f"EXAMPLE:\n"
            f"main.py\n"
            f"import pygame\n"
            f"pygame.init()\n"
            f"screen = pygame.display.set_mode((800,600))\n"
            f"clock = pygame.time.Clock()\n"
            f"running = True\n"
            f"while running:\n"
            f"    for event in pygame.event.get():\n"
            f"        if event.type == pygame.QUIT: running = False\n"
            f"    pygame.display.flip()\n"
            f"    clock.tick(60)\n"
            f"@@@\n"
            f"requirements.txt\n"
            f"pygame\n"
            f"@@@\n"
            f"§§§\n"
            f"Now write the complete project. Start immediately with the first filename.\n"
        ),
        "html": (
            f"You are an expert web developer. Create a professional static website.\n"
            f"PROJECT NAME: {name}\n"
            f"DESCRIPTION: {spec}\n"
            f"RULES:\n"
            f"- 3 SEPARATE files: index.html, css/style.css, js/script.js\n"
            f"- index.html: sticky navbar (logo + Home,Products,About,Contact + hamburger), hero section, "
            f"product cards grid (min 3), about section, contact form, footer\n"
            f"- css/style.css: CSS variables, Google Fonts @import, flexbox/grid, hover transitions, responsive\n"
            f"- js/script.js: hamburger toggle, smooth scroll, form validation, scroll animations\n"
            f"- NEVER put CSS or JS inside HTML\n"
            f"OUTPUT FORMAT: first line = relative path, then file content, then @@@. End with §§§.\n"
            f"EXAMPLE:\n"
            f"index.html\n"
            f"<!DOCTYPE html><html lang='en'><head><link rel='stylesheet' href='css/style.css'></head>"
            f"<body><nav><div class='logo'>{name}</div><ul><li><a href='#home'>Home</a></li></ul>"
            f"<div class='hamburger'><span></span><span></span><span></span></div></nav>"
            f"<script src='js/script.js'></script></body></html>\n"
            f"@@@\n"
            f"css/style.css\n"
            f":root{{--primary:#333;--accent:#f90;}} body{{font-family:'Inter',sans-serif;margin:0}}\n"
            f"@@@\n"
            f"js/script.js\n"
            f"document.querySelector('.hamburger').addEventListener('click',()=>{{"
            f"document.querySelector('nav ul').classList.toggle('open')}});\n"
            f"@@@\n"
            f"§§§\n"
            f"Now write the complete professional website. Start immediately with index.html.\n"
        ),
        "c": (
            f"You are an expert C developer targeting Windows with MSYS2/gcc.\n"
            f"PROJECT NAME: {name}\n"
            f"DESCRIPTION: {spec}\n"
            f"RULES:\n"
            f"- ONLY .c files. ABSOLUTELY NO HTML, CSS, JS, package.json files.\n"
            f"- Entry point: src/main.c\n"
            f"- Windows ONLY: use windows.h, conio.h. Use Sleep() not usleep(). Use system('cls') not system('clear').\n"
            f"- NEVER include unistd.h — it does not exist on Windows.\n"
            f"- For terminal games: use _kbhit() and _getch() from conio.h for real-time input.\n"
            f"OUTPUT FORMAT: first line = relative path, then file content, then @@@. End with §§§.\n"
            f"EXAMPLE:\n"
            f"src/main.c\n"
            f"#include <stdio.h>\n"
            f"#include <windows.h>\n"
            f"#include <conio.h>\n"
            f"int main() {{\n"
            f"    system(\"cls\");\n"
            f"    printf(\"Hello\\n\");\n"
            f"    Sleep(500);\n"
            f"    return 0;\n"
            f"}}\n"
            f"@@@\n"
            f"§§§\n"
            f"Now write the complete C project. Start immediately with src/main.c.\n"
        ),
        "cpp": (
            f"You are an expert C++ developer targeting Windows with MSYS2/g++.\n"
            f"PROJECT NAME: {name}\n"
            f"DESCRIPTION: {spec}\n"
            f"RULES:\n"
            f"- ONLY .cpp/.h files. ABSOLUTELY NO HTML, CSS, JS, package.json files.\n"
            f"- Entry point: src/main.cpp\n"
            f"- Windows ONLY: use windows.h, conio.h. Use Sleep() not usleep(). Use system('cls') not system('clear').\n"
            f"- NEVER include unistd.h — it does not exist on Windows.\n"
            f"- For terminal games: use _kbhit() and _getch() from conio.h for real-time input.\n"
            f"OUTPUT FORMAT: first line = relative path, then file content, then @@@. End with §§§.\n"
            f"EXAMPLE:\n"
            f"src/main.cpp\n"
            f"#include <iostream>\n"
            f"#include <windows.h>\n"
            f"#include <conio.h>\n"
            f"using namespace std;\n"
            f"int main() {{\n"
            f"    system(\"cls\");\n"
            f"    cout << \"Hello\" << endl;\n"
            f"    Sleep(500);\n"
            f"    return 0;\n"
            f"}}\n"
            f"@@@\n"
            f"§§§\n"
            f"Now write the complete C++ project. Start immediately with src/main.cpp.\n"
        ),
        "java": (
            f"You are an expert Java developer.\n"
            f"PROJECT NAME: {name}\n"
            f"DESCRIPTION: {spec}\n"
            f"RULES:\n"
            f"- ONLY .java files. ABSOLUTELY NO HTML, CSS, JS files.\n"
            f"- Entry point: src/Main.java with public static void main(String[] args)\n"
            f"OUTPUT FORMAT: first line = relative path, then file content, then @@@. End with §§§.\n"
            f"EXAMPLE:\n"
            f"src/Main.java\n"
            f"public class Main {{\n"
            f"    public static void main(String[] args) {{\n"
            f"        System.out.println(\"Hello\");\n"
            f"    }}\n"
            f"}}\n"
            f"@@@\n"
            f"§§§\n"
            f"Now write the complete Java project. Start immediately with src/Main.java.\n"
        ),
        "javascript": (
            f"You are an expert JavaScript developer.\n"
            f"PROJECT NAME: {name}\n"
            f"DESCRIPTION: {spec}\n"
            f"RULES:\n"
            f"- 3 SEPARATE files: index.html, css/style.css, js/script.js\n"
            f"- NEVER put CSS or JS inside HTML\n"
            f"OUTPUT FORMAT: first line = relative path, then file content, then @@@. End with §§§.\n"
            f"Now write the complete JavaScript project.\n"
        ),
        "rust": (
            f"You are an expert Rust developer.\n"
            f"PROJECT NAME: {name}\n"
            f"DESCRIPTION: {spec}\n"
            f"RULES: ONLY src/main.rs and Cargo.toml. No web files.\n"
            f"OUTPUT FORMAT: first line = relative path, then file content, then @@@. End with §§§.\n"
            f"Now write the complete Rust project.\n"
        ),
        "go": (
            f"You are an expert Go developer.\n"
            f"PROJECT NAME: {name}\n"
            f"DESCRIPTION: {spec}\n"
            f"RULES: ONLY .go files and go.mod. No web files.\n"
            f"OUTPUT FORMAT: first line = relative path, then file content, then @@@. End with §§§.\n"
            f"Now write the complete Go project.\n"
        ),
    }

    # Fallback generico
    default = (
        f"You are an expert {lang} developer.\n"
        f"PROJECT NAME: {name}\n"
        f"DESCRIPTION: {spec}\n"
        f"TECH: {tech_str}\n"
        f"RULES: Write only files for {lang}. No web files unless the project is a website.\n"
        f"OUTPUT FORMAT: first line = relative path, then file content, then @@@. End with §§§.\n"
        f"Now write the complete project.\n"
    )

    return PROMPTS.get(lang, default)


# ===================================================================
# GENERATE PROJECT
# ===================================================================

def generate_project(args: Dict[str, Any], workspace: Path, safe_resolve) -> Dict[str, Any]:
    name  = args.get("name") or args.get("project_name") or "new_project"
    spec  = args.get("description") or args.get("spec", "")
    techs = args.get("technologies", [])

    base_dir = Path.home() / "PyLineWorkspace"
    base_dir.mkdir(parents=True, exist_ok=True)
    target = base_dir / name
    target.mkdir(parents=True, exist_ok=True)

    print(f"\n   Generating project: {name}")
    print(f"   Path: {target}\n")

    try:
        # Step 1 — README
        print("   Step 1/4: Writing README...")
        readme = f"# {name}\n\n{spec}\n\n## Tecnologie\n\n"
        readme += "\n".join(f"- {t}" for t in techs) if techs else "- Auto-rilevate\n"
        (target / "README.md").write_text(readme, encoding="utf-8")
        print("   README.md written")

        # Step 2 — Costruzione prompt specifico per linguaggio
        print("\n Step 2/4: Costruzione prompt...")
        lang_hint = detect_lang_from_user_text(spec + " " + " ".join(techs), techs)
        print(f"   Linguaggio rilevato: {lang_hint}")
        prompt = build_prompt_for_lang(lang_hint, name, spec, techs)

        # Step 3 — Generazione
        print("\n Step 3/4: Generazione con Gemma...")
        t0  = time.time()
        raw = _call_gemma(prompt, max_tokens=6144)
        print(f" Completato in {time.time()-t0:.1f}s")

        files = _extract_files_from_output(raw, prompt)
        print(f"   File estratti: {len(files)}")

        if len(files) == 0:
            print(" Nessun file valido — retry con prompt semplificato...")
            simple = (
                f"Write a complete {lang_hint} project called '{name}'.\n"
                f"Description: {spec}\n"
                "For each file: first line = filename, then file content, then write @@@ on its own line.\n"
                "After all files write §§§. Start now."
            )
            raw   = _call_gemma(simple, max_tokens=4096)
            files = _extract_files_from_output(raw, simple)
            if len(files) == 0:
                print("   Generation failed: no files extracted from model output.")

        # Step 4 — Scrittura file
        print("\n Step 4/4: Scrittura file...")
        created = []
        for fname, body in files:
            fpath = (target / fname).resolve()
            if not str(fpath).startswith(str(target.resolve())):
                print(f" Path non sicuro saltato: {fname}")
                continue
            body = re.sub(r'\s*§§§\s*$', '', body).rstrip()
            if len(body.strip()) < 3:
                continue
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(body, encoding="utf-8")
            created.append(str(fpath.relative_to(target)))
            print(f"   {fpath.relative_to(target)}")

        all_files  = [str(f) for f in target.rglob("*") if f.is_file()]
        final_lang = detect_language(all_files)
        ensure_support_files(target, final_lang)

        COMPILED_LANGS = {"c", "cpp", "csharp", "java", "go", "rust"}
        if final_lang in COMPILED_LANGS:
            success, run_out = _print_compile_instructions(target, final_lang)
        elif final_lang == "python":
            print(f"\n Test esecuzione...")
            success, run_out = build_and_run(final_lang, target)
            print(f"{'' if success else ''} {run_out}")
            # Chiedi se compilare in exe
            print(f"\n Vuoi compilare il progetto in .exe con PyInstaller? [y/N]")
            choice = input("Scelta: ").strip().lower()
            if choice == "y":
                try:
                    subprocess.run([sys.executable, "-m", "PyInstaller", "--version"],
                                   capture_output=True, check=True)
                except Exception:
                    print("  Installo PyInstaller...")
                    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
                main_py = target / "main.py"
                if not main_py.exists():
                    candidates = list(target.rglob("main.py"))
                    if candidates:
                        main_py = candidates[0]
                if main_py.exists():
                    dist_dir = target / "dist"
                    print(f" Compilazione in corso... (1-2 minuti)")
                    result = subprocess.run(
                        [sys.executable, "-m", "PyInstaller", "--onefile",
                         "--distpath", str(dist_dir),
                         "--workpath", str(target / "build"),
                         "--specpath", str(target),
                         "--name", target.name, str(main_py)],
                        capture_output=True, text=True, timeout=300, cwd=str(target)
                    )
                    if result.returncode == 0:
                        exe = dist_dir / f"{target.name}.exe"
                        if exe.exists():
                            print(f" Compilato: {exe} ({round(exe.stat().st_size/1e6,1)} MB)")
                            run_out = f"exe: {exe}"
                        else:
                            print(f" Compilato in {dist_dir}")
                    else:
                        print(f" Errore PyInstaller:\n{result.stderr[-400:]}")
                else:
                    print(" main.py non trovato, skip compilazione")
        else:
            print(f"\n Test esecuzione...")
            success, run_out = build_and_run(final_lang, target)
            print(f"{'' if success else ''} {run_out}")

        print(f"\n{'='*60}")
        print(f" Progetto '{name}' generato in: {target}")
        print(f"{'='*60}\n")

        return {
            "status":        "ok" if created else "warning",
            "project":       str(target),
            "language":      final_lang,
            "created_files": created,
            "run_output":    run_out,
            "success":       success,
        }

    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "reason": str(e)}


# ===================================================================
# REGISTRAZIONE
# ===================================================================

def register_actions() -> Dict[str, Any]:
    return {"generate_project": generate_project}