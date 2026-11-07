"""Compõe as faixas originais dos trailers. São sintetizadas aqui, sem amostras de terceiros.

Uso: python tools/gerar_musicas.py   (grava em static/music/)
O andamento de cada faixa precisa bater com MUSIC em roleflix/trailers.py.
"""
import math
import random
import subprocess
import tempfile
import wave
from array import array
from pathlib import Path

import imageio_ffmpeg

RATE = 22050
OUT = Path(__file__).resolve().parent.parent / "static" / "music"
NOTES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def freq(note, octave):
    return 440 * 2 ** ((NOTES[note] + 12 * (octave - 4) - 9) / 12)


def chord(name):
    """Tríade a partir de nomes como Am ou F."""
    root = NOTES[name[0]]
    third = 3 if name.endswith("m") else 4
    return [root, root + third, root + 7]


def pitch(semitone, octave):
    return 440 * 2 ** ((semitone + 12 * (octave - 4) - 9) / 12)


def tone(buf, start, length, hz, volume, attack=0.01, decay=2.0, harmonics=(1, 0.4, 0.15)):
    first = int(start * RATE)
    count = min(int(length * RATE), len(buf) - first)
    step = [2 * math.pi * hz * (i + 1) / RATE for i in range(len(harmonics))]
    for n in range(count):
        t = n / RATE
        env = min(1, t / attack) * math.exp(-decay * t) * min(1, (length - t) / 0.03)
        buf[first + n] += volume * env * sum(a * math.sin(s * n) for a, s in zip(harmonics, step))


def kick(buf, start, volume):
    first = int(start * RATE)
    phase = 0.0
    for n in range(min(int(0.22 * RATE), len(buf) - first)):
        t = n / RATE
        phase += 2 * math.pi * (45 + 90 * math.exp(-t * 28)) / RATE
        buf[first + n] += volume * math.exp(-t * 11) * math.sin(phase)


def noise(buf, start, length, volume, rng):
    first = int(start * RATE)
    last = 0.0
    for n in range(min(int(length * RATE), len(buf) - first)):
        white = rng.uniform(-1, 1)
        buf[first + n] += volume * math.exp(-n / RATE * 45) * (white - last)
        last = white


def aurora(buf, beat, bars, rng):
    """Cinematográfica: acordes longos, tímpano grave e arpejo que cresce."""
    progression = ["Am", "F", "C", "G"]
    for bar in range(bars):
        at = bar * 4 * beat
        notes = chord(progression[bar % 4])
        for semitone in notes:
            tone(buf, at, 4.3 * beat, pitch(semitone, 3), 0.11, attack=0.8, decay=0.25, harmonics=(1, 0.5, 0.25, 0.1))
        tone(buf, at, 4 * beat, pitch(notes[0], 2), 0.16, attack=0.2, decay=0.5)
        kick(buf, at, 0.6)
        if bar >= 8:
            for i in range(8):
                tone(buf, at + i * beat / 2, beat, pitch(notes[i % 3], 5), 0.055, decay=4)
        if bar >= 16 and bar % 2:
            kick(buf, at + 3 * beat, 0.45)


def festa(buf, beat, bars, rng):
    """Divertida: batida constante, baixo saltado e melodia curta."""
    progression = ["C", "G", "Am", "F"]
    hook = [0, 2, 1, 2, 0, 1, 2, 1]
    for bar in range(bars):
        at = bar * 4 * beat
        notes = chord(progression[bar % 4])
        for i in range(4):
            kick(buf, at + i * beat, 0.62)
            noise(buf, at + (i + 0.5) * beat, 0.12, 0.2, rng)
            tone(buf, at + (i + 0.5) * beat, beat * 0.4, pitch(notes[0], 2), 0.2, decay=6)
        for semitone in notes:
            tone(buf, at + 1.5 * beat, beat * 0.9, pitch(semitone, 4), 0.05, decay=5)
            tone(buf, at + 3.5 * beat, beat * 0.9, pitch(semitone, 4), 0.05, decay=5)
        if bar >= 4:
            for i, index in enumerate(hook):
                tone(buf, at + i * beat / 2, beat * 0.45, pitch(notes[index], 5), 0.075, decay=7, harmonics=(1, 0.2))


def estrada(buf, beat, bars, rng):
    """Nostálgica: piano elétrico suave com vassourinha."""
    progression = ["G", "Em", "C", "D"]
    for bar in range(bars):
        at = bar * 4 * beat
        notes = chord(progression[bar % 4])
        tone(buf, at, 4 * beat, pitch(notes[0], 2), 0.15, attack=0.05, decay=0.9)
        for i in range(4):
            for offset, semitone in enumerate(notes):
                tone(buf, at + i * beat + offset * 0.018, 1.4 * beat, pitch(semitone, 4), 0.06, attack=0.012, decay=2.2, harmonics=(1, 0.25, 0.08, 0.04))
            noise(buf, at + i * beat, 0.16, 0.05 if i % 2 else 0.09, rng)
        if bar >= 8 and bar % 2 == 0:
            for i, index in enumerate((2, 1, 0, 1)):
                tone(buf, at + (i + 2) * beat, beat, pitch(notes[index], 5), 0.05, decay=3.5, harmonics=(1, 0.15))


def render(name, compose, bpm, bars):
    beat = 60 / bpm
    buf = [0.0] * int(bars * 4 * beat * RATE)
    compose(buf, beat, bars, random.Random(name))
    peak = max(abs(s) for s in buf) or 1
    samples = array("h", (int(32000 * math.tanh(1.1 * s / peak) / math.tanh(1.1)) for s in buf))
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "faixa.wav"
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(RATE)
            out.writeframes(samples.tobytes())
        target = OUT / f"{name}.m4a"
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-y", "-i", str(path), "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(target)], check=True, capture_output=True)
    print(name, f"{len(buf) / RATE:.0f}s", target.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    render("aurora", aurora, 76, 40)
    render("festa", festa, 124, 64)
    render("estrada", estrada, 92, 48)
