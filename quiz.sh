#!/usr/bin/env bash
# Génère une vidéo quiz « Vrai ou faux ? » à partir d'un fichier JSON.
# Usage : ./quiz.sh exemples/quiz-idees-recues.json
#   VOIX=Charon (autre voix Gemini)  AMBIANCE=suspense|calme|aucune  COMPTE=5 (secondes)
set -euo pipefail
[ $# -ge 1 ] || { echo "Usage : $0 fichier-quiz.json" >&2; exit 2; }
HERE="$(cd "$(dirname "$0")" && pwd)"
MPT_DIR="${MPT_DIR:-$HOME/MoneyPrinterTurbo}"
"$HERE/setup.sh"
ARGS=(--voix "${VOIX:-Puck}" --compte "${COMPTE:-3}")
case "${AMBIANCE:-calme}" in
  aucune) ;;
  *) BGM="$MPT_DIR/storage/bgm/ambiance-${AMBIANCE:-calme}.mp3"
     if [ ! -s "$BGM" ]; then
       mkdir -p "$(dirname "$BGM")"
       "$MPT_DIR/.venv/bin/python" "$HERE/tools/ambiance.py" "${AMBIANCE:-calme}" "/tmp/amb-$$.wav"
       ffmpeg -v error -y -i "/tmp/amb-$$.wav" -b:a 192k "$BGM" && rm -f "/tmp/amb-$$.wav"
     fi
     ARGS+=(--musique "$BGM") ;;
esac
mkdir -p "$HERE/videos"
dest="$HERE/videos/quiz-$(date +%Y%m%d-%H%M%S).mp4"
"$MPT_DIR/.venv/bin/python" "$HERE/tools/quiz.py" "$1" "$dest" "${ARGS[@]}"
echo "VIDEO_FILE=$dest"
