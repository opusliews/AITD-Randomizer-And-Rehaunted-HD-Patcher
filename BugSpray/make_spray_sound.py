"""Spray sound: the user's WAV -> a VOC in the game's own format (2026-10-28, Research/BugSpray.md).

Vanilla LISTSAMP.PAK entries are all the same shape: the 26-byte Creative header (version 0x010A,
checksum 0x1129), one type-1 block (time constant, codec 0 = 8-bit unsigned mono), then the
terminator 0. They are normalised to full scale (median peak 0.98, median active RMS about -16 dB).

This reads any PCM WAV (8/16/24/32-bit integer or 32-bit float, any rate, any channels), mixes to
mono, resamples with a windowed-sinc low-pass, trims the silence at both ends (with short fades),
normalises the peak to PEAK, and quantises to 8-bit unsigned with TPDF dither. For each rate it writes
spray_<rate>.voc and spray_<rate>_preview.wav (exactly the 8-bit samples the game will play).
  python Generated/BugSpray/make_spray_sound.py [References/Spray.wav]"""
import math, random, struct, sys, wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "sound"
SRC = HERE.parents[1] / "References" / "Spray.wav"
RATES = (8000, 11025, 16000)       # vanilla uses 4385..18181 Hz; DOS limit 64000 bytes per entry
PEAK = 0.95
TRIM_DB = -50.0                    # below this (re the peak, 5 ms windows) counts as silence
FADE_MS = 5
MAX_BYTES = 64000                  # INDARK.EXE: HQR_InitRessource("ListSamp", 64000, 30)


def read_wav(path: Path) -> tuple[int, list[float]]:
    """(rate, mono samples in -1..1)."""
    d = path.read_bytes()
    if d[:4] != b"RIFF" or d[8:12] != b"WAVE":
        raise SystemExit(f"{path}: not a WAV file")
    fmt = data = None
    i = 12
    while i + 8 <= len(d):
        cid, n = d[i:i + 4], struct.unpack_from("<I", d, i + 4)[0]
        if cid == b"fmt ":
            fmt = struct.unpack_from("<HHIIHH", d, i + 8)
            if fmt[0] == 0xFFFE:                         # WAVE_FORMAT_EXTENSIBLE: real tag in the GUID
                fmt = (struct.unpack_from("<H", d, i + 32)[0],) + fmt[1:]
        elif cid == b"data":
            data = d[i + 8:i + 8 + n]
        i += 8 + n + (n & 1)
    tag, ch, rate, _, align, bits = fmt
    width = bits // 8
    frames = len(data) // align
    if tag == 3 and bits == 32:
        v = struct.unpack(f"<{frames * ch}f", data[:frames * align])
    elif tag == 1 and bits == 8:
        v = [(b - 128) / 128 for b in data[:frames * align]]
    elif tag == 1 and bits in (16, 24, 32):
        scale = 2 ** (bits - 1)
        v = [int.from_bytes(data[k:k + width], "little", signed=True) / scale
             for k in range(0, frames * align, width)]
    else:
        raise SystemExit(f"{path}: unsupported WAV format (tag {tag}, {bits} bits)")
    return rate, [sum(v[f * ch:(f + 1) * ch]) / ch for f in range(frames)]


def resample(x: list[float], src: int, dst: int, half: int = 24) -> list[float]:
    """Windowed-sinc (Blackman) resampling; cutoff 0.9 of the lower Nyquist."""
    fc = 0.9 * min(src, dst) / 2 / src                   # cycles per input sample
    step = src / dst
    reach = int(math.ceil(half / (2 * fc)))              # input samples either side
    out = []
    for k in range(int(len(x) / step)):
        t = k * step
        c = int(t)
        acc = 0.0
        for j in range(max(0, c - reach + 1), min(len(x), c + reach + 1)):
            u = j - t
            w = 0.42 + 0.5 * math.cos(math.pi * u / reach) + 0.08 * math.cos(2 * math.pi * u / reach)
            s = 2 * fc if u == 0 else math.sin(2 * math.pi * fc * u) / (math.pi * u)
            acc += x[j] * s * w
        out.append(acc)
    return out


def trim(x: list[float], rate: int) -> list[float]:
    win = rate * 5 // 1000
    peak = max(abs(v) for v in x) or 1.0
    floor = peak * 10 ** (TRIM_DB / 20)
    loud = [i for i in range(0, len(x), win) if max(abs(v) for v in x[i:i + win]) > floor]
    a, b = loud[0], min(len(x), loud[-1] + win)
    y = x[a:b]
    f = rate * FADE_MS // 1000
    for i in range(f):
        y[i] *= i / f
        y[-1 - i] *= i / f
    return y


def to_u8(x: list[float], seed: int = 1) -> bytes:
    rnd = random.Random(seed)
    g = PEAK / max(abs(v) for v in x)
    return bytes(max(0, min(255, 128 + round(v * g * 127 + rnd.random() - rnd.random()))) for v in x)


def voc(rate: int, pcm: bytes) -> tuple[bytes, int]:
    """VOC laid out like the vanilla entries; returns (file, real rate)."""
    tc = 256 - round(1_000_000 / rate)
    size = len(pcm) + 2
    body = bytes([1, size & 255, size >> 8 & 255, size >> 16, tc, 0]) + pcm + b"\0"
    head = b"Creative Voice File\x1a" + struct.pack("<HHH", 26, 0x010A, 0x1129)
    return head + body, 1_000_000 // (256 - tc)


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC
    rate, x = read_wav(src)
    print(f"{src.name}: {len(x) / rate:.2f} s at {rate} Hz, peak {max(abs(v) for v in x):.2f}")
    OUT.mkdir(exist_ok=True)
    sys.path[:0] = [str(HERE.parent / "Sounds"), str(HERE.parent / "Patcher")]
    from extract_samples import voc_pcm
    for want in RATES:
        _, real = voc(want, b"")
        pcm = to_u8(trim(resample(x, rate, real), real))
        data, real = voc(want, pcm)
        back_rate, back = voc_pcm(data)                  # same parser as the sound browser
        assert (back_rate, back) == (real, pcm)
        (OUT / f"spray_{want}.voc").write_bytes(data)
        with wave.open(str(OUT / f"spray_{want}_preview.wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(1); w.setframerate(real); w.writeframes(pcm)
        ok = "OK" if len(data) <= MAX_BYTES else "TOO BIG"
        print(f"  {want:5d} Hz (real {real}): {len(pcm) / real:.2f} s, {len(data)} bytes ({ok})")


if __name__ == "__main__":
    main()
