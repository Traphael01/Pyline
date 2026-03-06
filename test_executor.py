from llama_cpp import Llama
from pathlib import Path

# 🔎 Ricerca automatica del modello GGUF in ./models
print("🔎 Ricerca modello GGUF in ./models ...")
gguf_files = list(Path("./models").rglob("*.gguf"))
if not gguf_files:
    print("❌ Nessun modello GGUF trovato in ./models — esegui prima download_Model.py")
    exit(1)

model_path = str(gguf_files[0])
print(f"✅ Modello trovato: {model_path}\n")

# 🚀 Caricamento modello con GPU offload
print("🚀 Caricamento modello...")
llm = Llama(
    model_path=model_path,
    n_ctx=2048,
    n_gpu_layers=-1,  # carica tutto sulla GPU
    verbose=False,
)
print("✅ Modello caricato!\n")

SYSTEM_PROMPT = "Sei un assistente AI ottimista."

print("💬 Chat con Gemma 3 4B — digita 'exit' per uscire.\n")

history = []

while True:
    user_input = input("Tu: ").strip()
    if not user_input:
        continue
    if user_input.lower() in {"exit", "quit"}:
        print("👋 Uscita.")
        break

    history.append({"role": "user", "content": user_input})

    response = llm.create_chat_completion(
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
        max_tokens=512,
        temperature=0.7,
    )

    answer = response["choices"][0]["message"]["content"].strip()
    history.append({"role": "assistant", "content": answer})

    print(f"\n🤖 Gemma: {answer}\n")