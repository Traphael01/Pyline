from huggingface_hub import hf_hub_download
import os

REPO_ID = "bartowski/google_gemma-3-4b-it-GGUF"
FILENAME = "google_gemma-3-4b-it-Q5_K.gguf"
MODEL_DIR = "./models"

os.makedirs(MODEL_DIR, exist_ok=True)

print(f"⬇️  Download {FILENAME} da {REPO_ID}...")
print("📦 Dimensione stimata: ~3.3 GB, attendere...")

path = hf_hub_download(
    repo_id=REPO_ID,
    filename=FILENAME,
    local_dir=MODEL_DIR,
)

print(f"✅ Modello scaricato in: {path}")