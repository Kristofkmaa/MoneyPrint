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

# Voix Gemini TTS (gratuite avec la clé Gemini). Edge TTS ne marche pas dans
# le cloud : il utilise des WebSockets, que le proxy réseau ne laisse pas passer.
case "${VOIX:-femme}" in
  homme) VOICE="gemini:Charon-Informative" ;;
  femme) VOICE="gemini:Kore-Firm" ;;
  *)     VOICE="$VOIX" ;;   # nom de voix complet, ex. gemini:Puck-Upbeat
esac
# Installe / configure si besoin (rapide si déjà fait)
"$HERE/setup.sh"

FORMAT="${FORMAT:-9:16}"
case "$FORMAT" in
  16:9) W=1920; H=1080 ;;
  1:1)  W=1080; H=1080 ;;
  *)    W=1080; H=1920 ;;
esac

# Musique d'ambiance : AMBIANCE=suspense | calme | aucune | auto (piste au hasard de MoneyPrinterTurbo)
MUSIQUE_ARGS=()
case "${AMBIANCE:-auto}" in
  suspense|calme)
    BGM="$MPT_DIR/storage/bgm/ambiance-${AMBIANCE}.mp3"
    if [ ! -s "$BGM" ]; then
      mkdir -p "$(dirname "$BGM")"
      "$MPT_DIR/.venv/bin/python" "$HERE/tools/ambiance.py" "$AMBIANCE" "/tmp/ambiance-$$.wav"
      ffmpeg -v error -y -i "/tmp/ambiance-$$.wav" -b:a 192k "$BGM" && rm -f "/tmp/ambiance-$$.wav"
    fi
    MUSIQUE_ARGS=(--bgm-type custom --bgm-file "$BGM" --bgm-volume "${VOLUME_MUSIQUE:-0.35}") ;;
  aucune) MUSIQUE_ARGS=(--bgm-type none) ;;
esac

TASK_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
NOM="video-$(date +%Y%m%d-%H%M%S)"
TASK_DIR="$MPT_DIR/storage/tasks/$TASK_ID"
cd "$MPT_DIR"

# MONTAGE=precis (défaut) : une image choisie par Gemini pour chaque phrase dite,
# coupée pile sur la voix (tools/storyboard.py). MONTAGE=rapide : montage
# d'origine de MoneyPrinterTurbo (plus rapide, images moins précises).
if [ "${MONTAGE:-precis}" = "precis" ]; then
  .venv/bin/python cli.py \
    --video-subject "$SUJET" \
    --video-language fr-FR \
    --video-source pixabay \
    --video-aspect "$FORMAT" \
    --voice-name "$VOICE" \
    --task-id "$TASK_ID" \
    "$@" \
    --stop-at audio
  case "${AMBIANCE:-auto}" in
    suspense|calme) MUSIQUE="$BGM" ;;
    aucune)         MUSIQUE="" ;;
    *)              MUSIQUE="$(ls resource/songs/*.mp3 | shuf -n 1)" ;;
  esac
  SB_ARGS=(--format "$FORMAT" --volume-musique "${VOLUME_MUSIQUE:-0.3}")
  [ -n "$MUSIQUE" ] && SB_ARGS+=(--musique "$MUSIQUE")
  [ "${AMBIANCE:-auto}" = "suspense" ] && SB_ARGS+=(--suspense)
  [ "${SANS_SOUS_TITRES:-0}" = "1" ] && SB_ARGS+=(--sans-sous-titres)
  mkdir -p "$OUT_DIR"
  dest="$OUT_DIR/${NOM}-1.mp4"
  .venv/bin/python "$HERE/tools/storyboard.py" "$TASK_DIR" "$dest" "${SB_ARGS[@]}"
  echo "VIDEO_FILE=$dest"
  exit 0
fi

# Les sous-titres de MoneyPrinterTurbo sont désactivés : leur minutage est
# estimé et se décale avec Gemini TTS. On les ajoute nous-mêmes juste après,
# calés sur les vraies pauses de la voix (tools/sync_subs.py).
.venv/bin/python cli.py \
  --video-subject "$SUJET" \
  --video-language fr-FR \
  --video-source pixabay \
  --video-aspect "$FORMAT" \
  --voice-name "$VOICE" \
  --task-id "$TASK_ID" \
  "${MUSIQUE_ARGS[@]}" \
  "$@" \
  --no-subtitle-enabled

SOUS_TITRES="$TASK_DIR/sous-titres.ass"
if [ "${SANS_SOUS_TITRES:-0}" != "1" ]; then
  .venv/bin/python "$HERE/tools/sync_subs.py" "$TASK_DIR" "$SOUS_TITRES" --width "$W" --height "$H"
fi

mkdir -p "$OUT_DIR"
n=0
for f in "$TASK_DIR"/final-*.mp4; do
  [ -s "$f" ] || continue
  n=$((n+1))
  dest="$OUT_DIR/${NOM}-${n}.mp4"
  FILTRES=()
  # Ambiance suspense : image plus sombre et désaturée + vignette
  [ "${AMBIANCE:-auto}" = "suspense" ] && FILTRES+=("eq=saturation=0.45:brightness=-0.06:contrast=1.12,vignette=PI/4.5")
  [ -s "$SOUS_TITRES" ] && FILTRES+=("ass=$SOUS_TITRES:fontsdir=$MPT_DIR/resource/fonts")
  if [ ${#FILTRES[@]} -gt 0 ]; then
    VF=$(IFS=,; echo "${FILTRES[*]}")
    ffmpeg -v error -y -i "$f" \
      -vf "$VF" \
      -c:v libx264 -preset medium -crf 20 -c:a copy -movflags +faststart "$dest"
  else
    cp "$f" "$dest"
  fi
  echo "VIDEO_FILE=$dest"
done
[ "$n" -gt 0 ] || { echo "❌ Aucune vidéo produite (voir $TASK_DIR)" >&2; exit 1; }
