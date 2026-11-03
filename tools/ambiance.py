"""Génère une musique d'ambiance libre de droits (synthèse, sans IA ni clé).

Usage : python ambiance.py <style> <sortie.wav> [--duree SECONDES]
Styles :
  suspense : nappes graves, battement sourd, souffle — true crime, mystère, enquête
  calme    : nappe douce en accord majeur — bien-être, nature, conseils
"""

from __future__ import annotations

import argparse
import wave

import numpy as np

SR = 44100


def lowpass(x: np.ndarray, k: int) -> np.ndarray:
    kernel = np.ones(k) / k
    return np.convolve(x, kernel, mode="same")


def pad(t, freqs, detune=0.15, lfo=0.05, phase=0.0):
    out = np.zeros_like(t)
    for i, f in enumerate(freqs):
        for d in (-detune, 0, detune):
            out += np.sin(2 * np.pi * (f + d) * t + i)
    swell = 0.6 + 0.4 * np.sin(2 * np.pi * lfo * t + phase)
    return out * swell / (len(freqs) * 3)


def suspense(t: np.ndarray, rng) -> np.ndarray:
    drone = pad(t, [55.0, 82.4], detune=0.3, lfo=0.03) * 0.9
    # Accord mineur sombre qui alterne lentement (Am -> Fm-ish), très doux
    chord_a = pad(t, [110.0, 130.8, 164.8], lfo=0.02)
    chord_b = pad(t, [87.3, 103.8, 130.8], lfo=0.02, phase=1.5)
    sel = 0.5 + 0.5 * np.sin(2 * np.pi * t / 24.0)
    chords = (chord_a * sel + chord_b * (1 - sel)) * 0.35
    # Battement de cœur grave toutes les 1,7 s
    beat = np.zeros_like(t)
    period = 1.7
    for start in np.arange(0.5, t[-1], period):
        for off, amp in ((0.0, 1.0), (0.28, 0.6)):
            i0 = int((start + off) * SR)
            n = int(0.35 * SR)
            if i0 + n >= len(t):
                break
            tt = np.arange(n) / SR
            beat[i0:i0 + n] += amp * np.sin(2 * np.pi * (48 + 30 * np.exp(-tt * 20)) * tt) * np.exp(-tt * 9)
    beat *= 0.45
    # Souffle / vent
    noise = lowpass(rng.standard_normal(len(t)), 400)
    noise = noise / (np.abs(noise).max() + 1e-9) * 0.25 * (0.6 + 0.4 * np.sin(2 * np.pi * 0.07 * t))
    # Note aiguë inquiétante, rare et lointaine
    eerie = np.sin(2 * np.pi * 659.3 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 5 * t))
    eerie *= np.clip(np.sin(2 * np.pi * t / 19.0), 0, None) ** 6 * 0.05
    return drone + chords + beat + noise + eerie


def calme(t: np.ndarray, rng) -> np.ndarray:
    chord_a = pad(t, [130.8, 164.8, 196.0, 261.6], lfo=0.04)
    chord_b = pad(t, [110.0, 146.8, 174.6, 220.0], lfo=0.04, phase=1.0)
    sel = 0.5 + 0.5 * np.sin(2 * np.pi * t / 16.0)
    pads = (chord_a * sel + chord_b * (1 - sel)) * 0.7
    air = lowpass(rng.standard_normal(len(t)), 200)
    air = air / (np.abs(air).max() + 1e-9) * 0.08
    return pads + air


STYLES = {"suspense": suspense, "calme": calme}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("style", choices=sorted(STYLES))
    ap.add_argument("out")
    ap.add_argument("--duree", type=float, default=240.0)
    a = ap.parse_args()

    rng = np.random.default_rng(7)
    t = np.arange(int(a.duree * SR)) / SR
    x = STYLES[a.style](t, rng)
    fade = int(2.5 * SR)
    env = np.ones_like(x)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    x = x * env
    x = x / (np.abs(x).max() + 1e-9) * 0.9
    pcm = (x * 32767).astype(np.int16)
    stereo = np.column_stack([pcm, np.roll(pcm, int(0.012 * SR))]).ravel()
    with wave.open(a.out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())
    print(f"Musique « {a.style} » ({a.duree:.0f} s) -> {a.out}")


if __name__ == "__main__":
    main()
