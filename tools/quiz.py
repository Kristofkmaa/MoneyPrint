"""Vidéo quiz « Vrai ou faux ? » : texte animé, compte à rebours, réponse révélée.

Entrée : un fichier JSON (voir exemples/quiz-idees-recues.json) :
{
  "titre": "VRAI OU FAUX ?",
  "intro": "Vrai ou faux ? Cinq idées reçues... Réponds avant la fin du compte à rebours !",
  "outro": "Alors, combien de bonnes réponses ? Dis-le en commentaire !",
  "fond_intro": "question mark",              # recherche Pixabay (anglais)
  "questions": [
    {"affirmation": "Les pieuvres ont trois cœurs.", "reponse": true,
     "explication": "Deux cœurs pompent le sang vers les branchies, le troisième vers le reste du corps.",
     "fond": "octopus"}
  ]
}

Usage (Python de MoneyPrinterTurbo) :
    python quiz.py quiz.json sortie.mp4 [--voix Puck] [--musique fichier.mp3] [--compte 3]
Variables : GEMINI_API_KEY, PIXABAY_API_KEY
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import storyboard  # noqa: E402  (recherche / téléchargement Pixabay)
import sync_subs  # noqa: E402  (alignement sur les pauses de la voix)

SR = 44100
W, H = 1080, 1920
FPS = 30
TTS_MODEL = "gemini-2.5-flash-preview-tts"
FONT = "Microsoft YaHei"


def log(msg: str) -> None:
    print(f"[quiz] {msg}", flush=True)


# --------------------------------------------------------------------------- audio
def tts(text: str, voice: str, out: Path) -> None:
    key = os.environ["GEMINI_API_KEY"]
    body = {
        "contents": [{"parts": [{"text":
            "Say in an energetic, upbeat French quiz-show host voice, "
            "with a clear pause between paragraphs:\n\n" + text}]}],
        "generationConfig": {"responseModalities": ["AUDIO"],
                             "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{TTS_MODEL}:generateContent"
    last = ""
    for attempt in range(6):
        r = requests.post(url, headers={"x-goog-api-key": key}, json=body, timeout=180)
        if r.status_code == 200:
            part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
            rate = 24000
            if "rate=" in part["mimeType"]:
                rate = int(part["mimeType"].split("rate=")[1].split(";")[0])
            pcm = out.with_suffix(".pcm")
            pcm.write_bytes(base64.b64decode(part["data"]))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(rate), "-ac", "1",
                            "-i", str(pcm), str(out)], check=True)
            return
        last = f"{r.status_code} {r.text[:300]}"
        time.sleep(10 * (attempt + 1))
    raise SystemExit(f"Synthèse vocale impossible : {last}")


def load_audio(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1",
                          "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def tick(freq=1400.0, dur=0.07, vol=0.35) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    return (np.sin(2 * np.pi * freq * t) * np.exp(-t * 60) * vol).astype(np.float32)


def ding(good: bool) -> np.ndarray:
    t = np.arange(int(0.6 * SR)) / SR
    notes = (880.0, 1318.5) if good else (523.3, 659.3)
    x = np.zeros_like(t)
    for i, f in enumerate(notes):
        start = int(i * 0.09 * SR)
        x[start:] += np.sin(2 * np.pi * f * t[: len(t) - start]) * np.exp(-t[: len(t) - start] * 6)
    return (x * 0.25).astype(np.float32)


# --------------------------------------------------------------------------- ASS
def ass_t(t: float) -> str:
    cs = int(round(max(t, 0) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def esc(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\n", "\\N")


ASS_HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Titre,{FONT},118,&H0000D7FF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,2,0,1,7,4,8,60,60,190,1
Style: Progres,{FONT},52,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,6,0,1,4,2,8,60,60,350,1
Style: Carte,{FONT},74,&H00FFFFFF,&H00FFFFFF,&HB4101010,&H00000000,1,0,0,0,100,100,0,0,3,28,0,5,110,110,0,1
Style: Bouton,{FONT},96,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,4,0,3,26,0,5,0,0,0,1
Style: Compte,{FONT},230,&H0000D7FF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,10,5,5,0,0,0,1
Style: Explic,{FONT},58,&H00FFFFFF,&H00FFFFFF,&HC8101010,&H00000000,1,0,0,0,100,100,0,0,3,22,0,2,100,100,190,1
Style: Grand,{FONT},96,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,7,4,5,50,50,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

GREEN = "&H0045B83B&"   # BGR
RED = "&H003C2FE0&"


def ev(layer, s, e, style, text):
    return f"Dialogue: {layer},{ass_t(s)},{ass_t(e)},{style},,0,0,0,,{text}"


def build_ass(data: dict, tl: dict, out: Path) -> None:
    lines = []
    total = tl["total"]
    n = len(data["questions"])
    titre = esc(data.get("titre", "VRAI OU FAUX ?"))
    # Intro : gros titre animé + accroche
    s, e = tl["intro"]
    lines.append(ev(2, s, e, "Grand", r"{\pos(540,820)\fscx40\fscy40\t(0,350,\fscx115\fscy115)\t(350,500,\fscx100\fscy100)\c&H0000D7FF&\fs128}" + titre))
    lines.append(ev(2, s + 0.4, e, "Grand", r"{\pos(540,1150)\fad(300,0)\fs70}" + esc(data.get("accroche_ecran", "Réponds avant la fin du compte à rebours !"))))
    # Titre permanent pendant les questions
    q0 = tl["questions"][0]["q"][0]
    lines.append(ev(1, q0, tl["outro"][0], "Titre", titre))
    for i, (q, seg) in enumerate(zip(data["questions"], tl["questions"])):
        qs, qe = seg["q"]
        cs, ce = seg["compte"]
        as_, ae = seg["a"]
        lines.append(ev(1, qs, ae, "Progres", f"QUESTION {i+1}/{n}"))
        lines.append(ev(2, qs, ae, "Carte", r"{\pos(540,800)\fad(200,0)}" + esc(q["affirmation"])))
        good = bool(q["reponse"])
        for label, x, colour, is_good in (("VRAI", 300, GREEN, good), ("FAUX", 780, RED, not good)):
            base = rf"{{\pos({x},1330)\3c{colour}"
            lines.append(ev(3, qs + 0.25, as_, "Bouton", base + r"\fad(200,0)}" + label))
            if is_good:
                lines.append(ev(3, as_, ae, "Bouton", base + r"\t(0,250,\fscx125\fscy125)\t(250,400,\fscx115\fscy115)}" + label))
            else:
                lines.append(ev(3, as_, ae, "Bouton", base + r"\t(0,250,\alpha&HB4&)}" + label))
        # Compte à rebours
        step = (ce - cs) / tl["compte_n"]
        for k in range(tl["compte_n"]):
            num = tl["compte_n"] - k
            lines.append(ev(4, cs + k * step, cs + (k + 1) * step, "Compte",
                            r"{\pos(540,1640)\fscx50\fscy50\t(0,120,\fscx120\fscy120)\t(120,250,\fscx100\fscy100)}" + str(num)))
        # Réponse
        verdict = "VRAI !" if good else "FAUX !"
        col = GREEN if good else RED
        lines.append(ev(4, as_, ae, "Explic", r"{\fad(250,0)}" + rf"{{\c{col}\fs96}}{verdict}{{\r}}\N" + esc(q["explication"])))
    s, e = tl["outro"]
    lines.append(ev(2, s, e, "Grand", r"{\pos(540,900)\fad(250,0)\fscx60\fscy60\t(0,300,\fscx100\fscy100)}" + esc(data.get("outro_ecran", data["outro"]))))
    out.write_text(ASS_HEADER + "\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- fonds
def background(query: str, dur: float, out: Path, work: Path, used: set) -> None:
    cands = [c for c in storyboard.pixabay("video", query, "vertical") if c["id"] not in used]
    if not cands:
        cands = [c for c in storyboard.pixabay("video", query.split()[0], "vertical") if c["id"] not in used]
    kind, media = "color", None
    if cands:
        c = cands[0]
        used.add(c["id"])
        media = storyboard.fetch(c["url"], work / f"{c['id']}.mp4")
        kind = "video"
    blur = "boxblur=6:1,eq=brightness=-0.28:saturation=0.8:contrast=0.9"
    cover = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
    if kind == "video":
        cmd = ["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", str(media), "-t", f"{dur:.3f}",
               "-an", "-vf", f"{cover},{blur},fps={FPS}"]
    else:
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x1a1440:s={W}x{H}:r={FPS}",
               "-t", f"{dur:.3f}"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, check=True)


# --------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("quiz", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--voix", default="Puck")
    ap.add_argument("--musique", type=Path)
    ap.add_argument("--volume-musique", type=float, default=0.18)
    ap.add_argument("--compte", type=int, default=3, help="durée du compte à rebours (s)")
    a = ap.parse_args()

    data = json.loads(a.quiz.read_text(encoding="utf-8"))
    qs = data["questions"]
    work = Path(tempfile.mkdtemp(prefix="quiz-"))

    # 1. Une seule synthèse vocale pour tout le texte, découpée ensuite
    blocks = [data["intro"]]
    for i, q in enumerate(qs, 1):
        blocks.append(f"Question {i}. {q['affirmation']}")
        blocks.append(("Vrai ! " if q["reponse"] else "Faux ! ") + q["explication"])
    blocks.append(data["outro"])
    voice_file = work / "voix.wav"
    log(f"synthèse vocale ({len(blocks)} blocs)...")
    tts("\n\n".join(blocks), a.voix, voice_file)
    times = sync_subs.align(blocks, voice_file)
    voice = load_audio(voice_file)
    dur_v = len(voice) / SR

    # 2. Ligne de temps : chaque bloc + compte à rebours après chaque question
    pieces, t = [], 0.0
    tl = {"questions": [], "compte_n": a.compte}
    effects = []  # (temps, signal)

    def seg(i):
        start = 0.0 if i == 0 else times[i][0] - 0.12
        end = times[i + 1][0] - 0.12 if i + 1 < len(times) else dur_v
        return voice[int(start * SR): int(end * SR)]

    def put(x):
        nonlocal t
        pieces.append(x)
        s = t
        t += len(x) / SR
        return s, t

    tl["intro"] = put(seg(0))
    for qi, q in enumerate(qs):
        qseg = put(seg(1 + 2 * qi))
        cstart = t
        silence = np.zeros(int(a.compte * SR), dtype=np.float32)
        cseg = put(silence)
        for k in range(a.compte):
            effects.append((cstart + k, tick(1500 if k < a.compte - 1 else 1100)))
        aseg = put(seg(2 + 2 * qi))
        effects.append((aseg[0], ding(True)))
        tl["questions"].append({"q": qseg, "compte": cseg, "a": aseg})
    tl["outro"] = put(np.concatenate([seg(len(blocks) - 1), np.zeros(int(1.0 * SR), np.float32)]))
    tl["total"] = t

    mix = np.concatenate(pieces)
    for at, sig in effects:
        i0 = int(at * SR)
        mix[i0:i0 + len(sig)] += sig[: max(0, len(mix) - i0)]
    if a.musique and a.musique.exists():
        bgm = load_audio(a.musique)
        reps = int(np.ceil(len(mix) / len(bgm)))
        bgm = np.tile(bgm, reps)[: len(mix)] * a.volume_musique
        fade = int(2 * SR)
        bgm[-fade:] *= np.linspace(1, 0, fade)
        mix = mix + bgm
    mix = np.clip(mix / max(1.0, np.abs(mix).max() / 0.95), -1, 1)
    audio_out = work / "audio.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-",
                    str(audio_out)], input=mix.astype(np.float32).tobytes(), check=True)
    log(f"audio : {tl['total']:.1f} s")

    # 3. Fonds vidéo : un par question (flous et assombris pour la lisibilité)
    used: set = set()
    parts = []
    spans = [("intro", tl["intro"][0], tl["questions"][0]["q"][0], data.get("fond_intro", qs[0]["fond"]))]
    for qi, q in enumerate(qs):
        end = tl["questions"][qi + 1]["q"][0] if qi + 1 < len(qs) else tl["outro"][0]
        spans.append((f"q{qi}", tl["questions"][qi]["q"][0], end, q["fond"]))
    spans.append(("outro", tl["outro"][0], tl["total"], data.get("fond_outro", data.get("fond_intro", qs[0]["fond"]))))
    for name, s, e, query in spans:
        p = work / f"fond_{name}.mp4"
        background(query, e - s, p, work, used)
        parts.append(p)
        log(f"fond {name} ({e - s:.1f}s) : {query}")
    lst = work / "liste.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
    fonds = work / "fonds.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                    str(fonds)], check=True)

    # 4. Textes animés + assemblage final
    ass = work / "quiz.ass"
    build_ass(data, tl, ass)
    fonts = Path.home() / "MoneyPrinterTurbo/resource/fonts"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(fonds), "-i", str(audio_out),
                    "-vf", f"ass={ass}:fontsdir={fonts}", "-map", "0:v", "-map", "1:a",
                    "-t", f"{tl['total']:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                    str(a.out)], check=True)
    log(f"✅ vidéo -> {a.out}")


if __name__ == "__main__":
    main()
