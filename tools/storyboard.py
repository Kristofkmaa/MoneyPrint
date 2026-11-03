"""Montage « image = parole » : chaque phrase dite par la voix a son propre plan.

Pour chaque ligne de sous-titre :
  1. Gemini propose des recherches précises en anglais (ce qu'on doit VOIR) ;
  2. on récupère des candidats Pixabay (vidéos d'abord, photos en secours) ;
  3. Gemini regarde les miniatures et choisit celle qui illustre le mieux la phrase ;
  4. le plan est coupé pile sur la durée de la phrase (minutage de sync_subs).
Puis on assemble, on mixe voix + musique, on incruste les sous-titres.

Usage (Python de MoneyPrinterTurbo) :
    python storyboard.py <dossier_tache> <sortie.mp4> [--format 9:16]
        [--musique fichier.mp3] [--volume-musique 0.3] [--suspense] [--sans-sous-titres]
Variables : GEMINI_API_KEY, PIXABAY_API_KEY, GEMINI_MODEL (défaut gemini-3.5-flash)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_subs  # noqa: E402

FPS = 30
MIN_SHOT = 1.6  # en dessous, la ligne partage le plan de la suivante
MODELS = [os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"), "gemini-3.5-flash-lite", "gemini-3.5-flash"]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"


def log(msg: str) -> None:
    print(f"[storyboard] {msg}", flush=True)


# --------------------------------------------------------------------------- Gemini
def gemini(parts: list, json_out: bool = True) -> str:
    key = os.environ["GEMINI_API_KEY"]
    body = {"contents": [{"parts": parts}]}
    if json_out:
        body["generationConfig"] = {"responseMimeType": "application/json"}
    last = ""
    for attempt in range(8):
        model = MODELS[attempt % len(MODELS)]
        try:
            r = requests.post(GEMINI_URL.format(model), headers={"x-goog-api-key": key},
                              json=body, timeout=90)
            if r.status_code == 200:
                cand = r.json()["candidates"][0]["content"]["parts"]
                return "".join(p.get("text", "") for p in cand)
            last = f"{r.status_code} {r.text[:200]}"
        except requests.RequestException as e:  # réseau
            last = str(e)
        time.sleep(min(4 * (attempt + 1), 20))
    raise RuntimeError(f"Gemini indisponible : {last}")


def plan_queries(full_script: str, shots: list[dict]) -> None:
    listing = "\n".join(f"{i}: {s['text']}" for i, s in enumerate(shots))
    prompt = f"""Tu prépares le montage d'une vidéo courte. Voici le script complet :
\"\"\"{full_script}\"\"\"

Voici les plans, un par phrase prononcée :
{listing}

Pour CHAQUE plan, donne 3 recherches en ANGLAIS pour une banque de vidéos/photos
(Pixabay), de la plus précise à la plus générale. Chaque recherche fait 1 à 3 mots
et décrit ce qu'on doit VOIR à l'écran pendant cette phrase, concrètement
(ex. « astronaut tears » -> « water droplet zero gravity », « astronaut face »).
Tiens compte du contexte des phrases voisines (un « elle » désigne ce dont on parle).
Pour l'accroche ou la conclusion, choisis une image forte liée au thème général.
Évite les noms propres que la banque ne connaît pas ; décris l'objet visible.

Réponds en JSON : {{"plans": [{{"i": 0, "voir": "description courte en français", "recherches": ["...", "...", "..."]}}, ...]}}"""
    data = json.loads(gemini([{"text": prompt}]))
    by_i = {p["i"]: p for p in data["plans"]}
    for i, s in enumerate(shots):
        p = by_i.get(i, {})
        s["voir"] = p.get("voir", s["text"])
        s["queries"] = [q for q in p.get("recherches", []) if q][:3] or [s["text"]]


# --------------------------------------------------------------------------- Pixabay
def pixabay(kind: str, q: str, orientation: str) -> list[dict]:
    key = os.environ["PIXABAY_API_KEY"]
    url = "https://pixabay.com/api/videos/" if kind == "video" else "https://pixabay.com/api/"
    params = {"key": key, "q": q[:100], "per_page": 12, "safesearch": "true"}
    if kind == "image":
        params.update(image_type="photo")
        if orientation != "any":
            params["orientation"] = orientation
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        hits = r.json().get("hits", [])
    except requests.RequestException:
        return []
    out = []
    for h in hits:
        if kind == "video":
            v = h["videos"]
            # « medium » (~1080p) suffit pour un rendu 1080x1920 et se télécharge 4x plus vite
            best = next((v[s] for s in ("medium", "large", "small") if v.get(s, {}).get("url")), None)
            if not best or not best.get("url"):
                continue
            out.append({"kind": "video", "id": f"v{h['id']}", "url": best["url"],
                        "thumb": (v.get("tiny") or best).get("thumbnail") or best.get("thumbnail"),
                        "w": best["width"], "h": best["height"], "duration": h.get("duration", 0),
                        "tags": h.get("tags", "")})
        else:
            out.append({"kind": "image", "id": f"i{h['id']}", "url": h["largeImageURL"],
                        "thumb": h["previewURL"], "w": h["imageWidth"], "h": h["imageHeight"],
                        "duration": 0, "tags": h.get("tags", "")})
    return out


def fetch(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    return dest


def choose(shot: dict, cands: list[dict], cache: Path) -> dict | None:
    if not cands:
        return None
    parts = [{"text": f"""Phrase dite par la voix : « {shot['text']} »
Ce qu'on devrait voir : {shot['voir']}
Voici {len(cands)} images candidates numérotées. Choisis celle qui illustre le
plus exactement la phrase (sujet visible, pas juste l'ambiance). Évite le texte
incrusté, les logos, les visages en gros plan sans rapport.
Réponds en JSON : {{"choix": <numéro>, "note": <0 à 10>}}"""}]
    for n, c in enumerate(cands):
        try:
            thumb = fetch(c["thumb"], cache / f"thumb_{c['id']}.jpg")
        except requests.RequestException:
            continue
        parts.append({"text": f"Image {n} ({c['kind']}) :"})
        parts.append({"inline_data": {"mime_type": "image/jpeg",
                                      "data": base64.b64encode(thumb.read_bytes()).decode()}})
    try:
        res = json.loads(gemini(parts))
        k = int(res.get("choix", 0))
        c = cands[k] if 0 <= k < len(cands) else cands[0]
        c["note"] = res.get("note", "?")
        return c
    except (RuntimeError, ValueError, KeyError, json.JSONDecodeError):
        return cands[0]


def candidates_for(shot: dict, used: set[str], orientation: str) -> list[dict]:
    pool: list[dict] = []
    seen: set[str] = set()
    for q in shot["queries"]:
        for c in pixabay("video", q, orientation)[:4]:
            if c["id"] not in used and c["id"] not in seen:
                pool.append(c); seen.add(c["id"])
        if len(pool) >= 6:
            break
    # Les photos complètent quand les vidéos manquent ou sont peu nombreuses
    for q in shot["queries"][:2]:
        if len(pool) >= 8:
            break
        for c in pixabay("image", q, orientation)[:3]:
            if c["id"] not in used and c["id"] not in seen:
                pool.append(c); seen.add(c["id"])
    return pool[:8]


# --------------------------------------------------------------------------- Rendu
def render_shot(media: Path, kind: str, dur: float, out: Path, W: int, H: int) -> None:
    cover = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
    if kind == "video":
        cmd = ["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", str(media),
               "-t", f"{dur:.3f}", "-an", "-vf", f"{cover},fps={FPS}"]
    else:
        frames = max(int(round(dur * FPS)), 1)
        zoom_in = random.random() < 0.5
        z = "min(1+0.12*on/{f},1.12)" if zoom_in else "max(1.12-0.12*on/{f},1)"
        z = z.format(f=frames)
        cmd = ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(media), "-t", f"{dur:.3f}",
               "-vf", f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
                      f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},setsar=1"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, check=True)


def build_shots(lines: list[str], times: list[tuple[float, float]], total: float) -> list[dict]:
    shots: list[dict] = []
    for text, (s, e) in zip(lines, times):
        if shots and (shots[-1]["e"] - shots[-1]["s"]) < MIN_SHOT:
            shots[-1]["text"] += " " + text
            shots[-1]["e"] = e
        else:
            shots.append({"text": text, "s": s, "e": e})
    if len(shots) > 1 and shots[-1]["e"] - shots[-1]["s"] < MIN_SHOT:
        last = shots.pop()
        shots[-1]["text"] += " " + last["text"]
        shots[-1]["e"] = last["e"]
    # Les plans se touchent : chacun dure jusqu'au début du suivant
    for i, sh in enumerate(shots):
        sh["start"] = 0.0 if i == 0 else sh["s"]
        sh["end"] = shots[i + 1]["s"] if i + 1 < len(shots) else total
        sh["dur"] = sh["end"] - sh["start"]
    return shots


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task_dir", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--format", default="9:16", choices=["9:16", "16:9", "1:1"])
    ap.add_argument("--musique", type=Path)
    ap.add_argument("--volume-musique", type=float, default=0.3)
    ap.add_argument("--suspense", action="store_true")
    ap.add_argument("--sans-sous-titres", action="store_true")
    ap.add_argument("--fonts", type=Path, default=Path.home() / "MoneyPrinterTurbo/resource/fonts")
    a = ap.parse_args()

    W, H = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}[a.format]
    orientation = {"9:16": "vertical", "16:9": "horizontal", "1:1": "any"}[a.format]
    work = a.task_dir / "storyboard"
    work.mkdir(exist_ok=True)
    audio = a.task_dir / "audio.mp3"
    total = sync_subs.audio_duration(audio)

    lines = sync_subs.script_lines(a.task_dir)
    times = sync_subs.align(lines, audio)
    ass = a.task_dir / "sous-titres.ass"
    sync_subs.write_ass(lines, times, ass, W, H, "Microsoft YaHei")

    shots = build_shots(lines, times, total)
    full_script = json.loads((a.task_dir / "script.json").read_text(encoding="utf-8"))["script"]
    log(f"{len(shots)} plans à illustrer, recherche des visuels...")
    plan_queries(full_script, shots)

    used: set[str] = set()
    parts_list = []
    for i, sh in enumerate(shots):
        cands = candidates_for(sh, used, orientation)
        pick = choose(sh, cands, work)
        if pick is None:
            raise SystemExit(f"Aucun visuel trouvé pour : {sh['text']}")
        used.add(pick["id"])
        ext = ".mp4" if pick["kind"] == "video" else ".jpg"
        media = fetch(pick["url"], work / f"{pick['id']}{ext}")
        part = work / f"plan_{i:02d}.mp4"
        render_shot(media, pick["kind"], sh["dur"], part, W, H)
        parts_list.append(part)
        log(f"plan {i+1}/{len(shots)} ({sh['dur']:.1f}s) « {sh['text'][:50]} » -> "
            f"{pick['kind']} [{pick['tags'][:40]}] note {pick.get('note', '?')}")

    concat = work / "liste.txt"
    concat.write_text("".join(f"file '{p.name}'\n" for p in parts_list))
    visuels = work / "visuels.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
                    "-c", "copy", str(visuels)], check=True)

    vf = []
    if a.suspense:
        vf.append("eq=saturation=0.45:brightness=-0.06:contrast=1.12,vignette=PI/4.5")
    if not a.sans_sous_titres:
        vf.append(f"ass={ass}:fontsdir={a.fonts}")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(visuels), "-i", str(audio)]
    graph = [f"[0:v]{','.join(vf) if vf else 'null'}[v]"]
    if a.musique and a.musique.exists():
        cmd += ["-stream_loop", "-1", "-i", str(a.musique)]
        graph.append(f"[2:a]volume={a.volume_musique},afade=t=out:st={max(total-2.5,0):.2f}:d=2.5[m]")
        graph.append("[1:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
    else:
        graph.append("[1:a]anull[a]")
    cmd += ["-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]"]
    cmd += ["-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(a.out)]
    subprocess.run(cmd, check=True)
    log(f"✅ vidéo -> {a.out}")


if __name__ == "__main__":
    main()
