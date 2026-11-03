"""Sous-titres calés exactement sur la voix.

Gemini TTS ne donne pas le minutage des mots : MoneyPrinterTurbo estime alors
les temps au prorata du texte, et les sous-titres se décalent. Ici on repère les
vraies pauses dans l'audio (ffmpeg silencedetect) et on place chaque coupure de
sous-titre sur la pause la plus plausible (programmation dynamique). Le texte
affiché est exactement celui du script lu par la voix.

Usage (avec le Python de MoneyPrinterTurbo) :
    python sync_subs.py <dossier_tache> <sortie.ass> [--width W --height H]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MPT_DIR = Path.home() / "MoneyPrinterTurbo"
sys.path.insert(0, str(MPT_DIR))
from app.utils import utils  # noqa: E402


def script_lines(task_dir: Path) -> list[str]:
    script = json.loads((task_dir / "script.json").read_text(encoding="utf-8"))["script"]
    text = utils.normalize_script_for_subtitle_matching(script)
    lines = [l.strip() for l in utils.split_string_by_punctuations(text) if l.strip()]
    return lines


def audio_duration(audio: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(out.strip())


def silences(audio: Path, noise_db: int = -35, min_d: float = 0.08) -> list[tuple[float, float]]:
    err = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(audio), "-af",
         f"silencedetect=noise={noise_db}dB:d={min_d}", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    out = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else None
        out.append((s, e))
    return out


def spoken_len(line: str) -> int:
    """Longueur « parlée » approximative : un nombre se dit beaucoup plus long
    qu'il ne s'écrit (1968 = « mille neuf cent soixante-huit »)."""
    n = 0
    for tok in re.findall(r"\d+|[^\d\s]", line):
        if tok.isdigit():
            n += 7 * len(tok)
        else:
            n += 1
    return max(n, 1)


def align(lines: list[str], audio: Path) -> list[tuple[float, float]]:
    dur = audio_duration(audio)
    sil = silences(audio)
    sil = [(s, e if e is not None else dur) for s, e in sil]

    speech_start, speech_end = 0.0, dur
    if sil and sil[0][0] <= 0.05:
        speech_start = sil[0][1]
        sil = sil[1:]
    if sil and sil[-1][1] >= dur - 0.05:
        speech_end = sil[-1][0]
        sil = sil[:-1]
    cands = [(s, e) for s, e in sil if speech_start < s and e < speech_end]

    n = len(lines)
    if n == 1:
        return [(speech_start, speech_end)]

    k, m = n - 1, len(cands)
    if m < k:
        # Pas assez de pauses détectées : on retombe sur le prorata du texte.
        weights = [max(len(l), 1) for l in lines]
        total, acc, bounds = sum(weights), 0, []
        for w in weights[:-1]:
            acc += w
            t = speech_start + (speech_end - speech_start) * acc / total
            bounds.append((t, t))
    else:
        # Points de coupure possibles : début, chaque pause, fin.
        pts = [(speech_start, speech_start)] + cands + [(speech_end, speech_end)]

        def speech_between(a: int, b: int) -> float:
            """Temps de parole (pauses internes exclues) entre deux points."""
            start, end = pts[a][1], pts[b][0]
            inner = sum(e - s for s, e in pts[a + 1:b])
            return max(end - start - inner, 0.0)

        chars = [spoken_len(l) for l in lines]
        rate = speech_between(0, len(pts) - 1) / sum(chars)  # secondes par caractère

        def seg_cost(j: int, a: int, b: int) -> float:
            exp = chars[j] * rate
            d = speech_between(a, b)
            return 12 * ((d - exp) / (exp + 0.4)) ** 2

        def bonus(c: int) -> float:
            s, e = pts[c]
            return 2.0 * min(e - s, 0.8)

        INF = float("inf")
        P = len(pts)
        # dp[j][c] : meilleur coût pour placer la fin de la ligne j sur le point c
        dp = [[INF] * P for _ in range(n)]
        back = [[-1] * P for _ in range(n)]
        for c in range(1, P - 1):
            dp[0][c] = seg_cost(0, 0, c) - bonus(c)
        for j in range(1, n - 1):
            for c in range(j + 1, P - 1):
                best, arg = INF, -1
                for a in range(j, c):
                    v = dp[j - 1][a]
                    if v < INF:
                        v += seg_cost(j, a, c)
                        if v < best:
                            best, arg = v, a
                if arg >= 0:
                    dp[j][c] = best - bonus(c)
                    back[j][c] = arg
        best, arg = INF, -1
        for a in range(n - 1, P - 1):
            v = dp[n - 2][a]
            if v < INF:
                v += seg_cost(n - 1, a, P - 1)
                if v < best:
                    best, arg = v, a
        chosen = [0] * k
        c = arg
        for j in range(n - 2, -1, -1):
            chosen[j] = c
            c = back[j][c]
        bounds = [pts[c] for c in chosen]

    times = []
    start = speech_start
    for j in range(n):
        if j < k:
            end = bounds[j][0]
            times.append((start, end))
            start = bounds[j][1]
        else:
            times.append((start, speech_end))
    return times


def ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def write_ass(lines, times, out: Path, width: int, height: int, font: str) -> None:
    size = round(height * 0.033)
    margin_v = round(height * 0.16)
    margin_h = round(width * 0.07)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,{max(2, size // 18)},1,2,{margin_h},{margin_h},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    body = []
    for text, (s, e) in zip(lines, times):
        text = text.replace("\n", " ").replace("{", "(").replace("}", ")")
        body.append(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Default,,0,0,0,,{text}")
    out.write_text(header + "\n".join(body) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task_dir", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--font", default="Microsoft YaHei")
    a = ap.parse_args()

    lines = script_lines(a.task_dir)
    times = align(lines, a.task_dir / "audio.mp3")
    write_ass(lines, times, a.out, a.width, a.height, a.font)
    print(f"{len(lines)} sous-titres calés sur la voix -> {a.out}")


if __name__ == "__main__":
    main()
