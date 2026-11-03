#!/usr/bin/env bash
# Génère une vidéo à partir d'un sujet.
# Usage : ./video.sh "Sujet de la vidéo" [options supplémentaires de cli.py]
# Exemples :
#   ./video.sh "5 astuces pour mieux dormir"
#   VOIX=homme FORMAT=16:9 ./video.sh "L'histoire du café" --paragraph-number 3
set -euo pipefail

if [ $# -lt 1 ] || [ -z "$1" ]; then
  echo "Usage : $0 \"sujet\" [options cli.py]" >&2
  exit 2
fi
SUJET="$1"; shift

HERE="$(cd "$(dirname "$0")" && pwd)"
MPT_DIR="${MPT_DIR:-$HOME/MoneyPrinterTurbo}"
OUT_DIR="${OUT_DIR:-$HERE/videos}"

case "${VOIX:-femme}" in
  homme) VOICE="fr-FR-HenriNeural-Male" ;;
  *)     VOICE="fr-FR-DeniseNeural-Female" ;;
esac
FORMAT="${FORMAT:-9:16}"

# Installe / configure si besoin (rapide si déjà fait)
"$HERE/setup.sh"

TASK_ID="video-$(date +%Y%m%d-%H%M%S)"
cd "$MPT_DIR"
.venv/bin/python cli.py \
  --video-subject "$SUJET" \
  --video-language fr-FR \
  --video-source pixabay \
  --video-aspect "$FORMAT" \
  --voice-name "$VOICE" \
  --task-id "$TASK_ID" \
  "$@"

mkdir -p "$OUT_DIR"
n=0
for f in storage/tasks/"$TASK_ID"/final-*.mp4; do
  [ -s "$f" ] || continue
  n=$((n+1))
  dest="$OUT_DIR/${TASK_ID}-${n}.mp4"
  cp "$f" "$dest"
  echo "VIDEO_FILE=$dest"
done
[ "$n" -gt 0 ] || { echo "❌ Aucune vidéo produite (voir storage/tasks/$TASK_ID)" >&2; exit 1; }
