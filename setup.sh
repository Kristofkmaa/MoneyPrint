#!/usr/bin/env bash
# Installe MoneyPrinterTurbo et le configure à partir des variables d'environnement.
# Sans risque à relancer : ne refait que ce qui manque.
set -euo pipefail

MPT_DIR="${MPT_DIR:-$HOME/MoneyPrinterTurbo}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.5-flash}"

if [ ! -f "$MPT_DIR/cli.py" ]; then
  echo "[setup] Téléchargement de MoneyPrinterTurbo..."
  git clone --depth 1 https://github.com/harry0703/MoneyPrinterTurbo.git "$MPT_DIR"
fi

cd "$MPT_DIR"
if [ ! -x .venv/bin/python ]; then
  echo "[setup] Installation des dépendances (quelques minutes)..."
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
  uv sync --frozen
fi

[ -f config.toml ] || cp config.example.toml config.toml
chmod 600 config.toml

missing=()
[ -n "${GEMINI_API_KEY:-}" ] || missing+=("GEMINI_API_KEY")
[ -n "${PIXABAY_API_KEY:-}" ] || missing+=("PIXABAY_API_KEY")
if [ ${#missing[@]} -gt 0 ]; then
  echo "[setup] ⚠ Variables manquantes : ${missing[*]}"
  echo "[setup]   Ajoute-les dans les réglages de l'environnement cloud (voir README)."
  exit 10
fi

GEMINI_MODEL="$GEMINI_MODEL" python3 - <<'PY'
import os, re
p = "config.toml"
t = open(p, encoding="utf-8").read()
def put(key, value):
    global t
    t, n = re.subn(rf"(?m)^{key}\s*=.*$", f"{key} = {value}", t, count=1)
    if not n:
        raise SystemExit(f"clé introuvable dans config.toml : {key}")
put("llm_provider", '"gemini"')
put("gemini_api_key", '"%s"' % os.environ["GEMINI_API_KEY"])
put("gemini_model_name", '"%s"' % os.environ["GEMINI_MODEL"])
put("video_source", '"pixabay"')
put("pixabay_api_keys", '["%s"]' % os.environ["PIXABAY_API_KEY"])
open(p, "w", encoding="utf-8").write(t)
PY

echo "[setup] ✅ MoneyPrinterTurbo prêt dans $MPT_DIR"
