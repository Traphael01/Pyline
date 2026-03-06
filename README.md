# PyLine

A local AI assistant that controls your Windows PC through natural language.
Powered by Gemma 3 4B running entirely on your machine — no internet required after setup, no cloud, no API keys.

---

## What it can do

- Open apps, URLs, folders, and files
- Create, edit, rename, move, copy, and delete files and folders
- Generate code projects (Python, C/C++, HTML/CSS/JS, and more)
- Create Word, Excel, PowerPoint, and PDF documents
- Control screen brightness and take screenshots
- Monitor CPU and GPU temperatures, list and kill processes
- Clean temporary files and scan for heavy apps
- Set alarms with a fullscreen gorilla GIF
- Remember information across sessions
- Talk with a text-to-speech voice (optional)
- Analyze URLs for safety before opening them

---

## Requirements

- Windows 10 or 11
- Python 3.10 or higher — [python.org](https://www.python.org/downloads/)
  - During install, check **"Add Python to PATH"**
- At least 8 GB RAM (16 GB recommended)
- ~5 GB free disk space (3.3 GB model + dependencies)
- NVIDIA GPU optional but recommended for faster responses

---

## Installation

1. Download or clone this repository
2. Open the folder
3. Double-click **`install.exe`**

The installer will:
1. Install all Python dependencies
2. Try to install `llama-cpp-python` with CUDA support (NVIDIA GPU)
3. If CUDA fails, automatically fall back to the CPU version
4. Download the Gemma 3 4B model (~3.3 GB) into `./models/`

> The download may take several minutes. Do not close the window.

---

## GPU acceleration

The installer tries CUDA automatically. If your PC has an NVIDIA GPU and CUDA Toolkit installed, it will use it. Otherwise it falls back to CPU — everything still works, just slower.

To check which mode was installed:

```
python -c "from llama_cpp import Llama; print('ok')"
```

If you want to force CUDA after the fact:

```
pip uninstall llama-cpp-python -y
pip install llama-cpp-python==0.3.4 --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu122
```

---

## Running PyLine

Double-click **`PyLine.exe`** or run:

```
python pyline.py
```

At startup PyLine detects your GPU, loads the model, and shows the `pyline>` prompt.
Type `help` to see all available commands.

---

## Voice (optional)

Three voices are included in the `voices/` folder:

| Key | Voice |
|-----|-------|
| `female_ita` | Italian female (Paola) |
| `female_eng` | English female (LibriTTS) |
| `male_eng` | English male (Ryan) |

```
pyline> enable voice female ita
pyline> disable voice
pyline> voice status
```

---

## Example commands

```
pyline> open spotify
pyline> create file desktop/notes.txt with content hello
pyline> screenshot
pyline> how much ram am i using?
pyline> generate a snake game in python
pyline> create a powerpoint about AI with 4 slides
pyline> set alarm at 14:30 for drink water
pyline> clean system
pyline> temperatures
pyline> help
```

---

## Project structure

```
PyLine/
├── pyline.py              Main entry point
├── download_Model.py      Downloads the AI model
├── install.exe            Installer (run this first)
├── PyLine.exe             Launcher
├── requirements.txt       Python dependencies
├── models/                GGUF model files (created after install)
├── voices/                Piper TTS voice files
│   ├── fe_IT.onnx + fe_IT.json
│   ├── fe_US.onnx + fe_US.json
│   └── man_US.onnx + man_US.json
├── avgif/                 Alarm assets
│   ├── gorilla.gif
│   ├── samsung.mp3
│   └── brain.mp3
└── plugins/
    ├── __init__.py
    ├── io_actions.py      File operations + Office documents
    ├── open_actions.py    Open apps, URLs, folders
    ├── command_G.py       AI project generation
    ├── command_M.py       Memory and alarms
    ├── command_sys.py     System control and monitoring
    └── voice.py           TTS engine
```

---

## Known limitations

- **Temperature monitoring** needs [OpenHardwareMonitor](https://openhardwaremonitor.org/) running in background for full CPU data. GPU temperature works out of the box via nvidia-smi.
- **Screen brightness** works best on laptops. May not work on all desktop monitor setups.
- **wmi** is Windows-only — it installs automatically but requires Visual C++ Redistributable (already present on most systems).
- On machines with less than 8 GB RAM, the context window is automatically reduced to 4096 tokens.

---

## License

GPL-3.0

## Author

[Traphael01](https://github.com/Traphael01)
