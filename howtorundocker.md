# 1) Native Ollama on host (Metal)
brew install ollama
ollama serve &

# 2) Pull models (fast on M-series)
make models MODELS="moondream:latest,llava:7b,qwen2.5:7b-instruct"

# 3) Bring up gateway + infra
make up

# 4) Open the UI
open http://localhost:8080/ui#dashboard
