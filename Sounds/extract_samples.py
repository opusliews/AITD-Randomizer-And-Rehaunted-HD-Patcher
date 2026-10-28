"""Every sound effect of AITD1 as WAV, plus a local browser page (2026-10-28).

LISTSAMP.PAK holds 101 Creative VOC samples (8-bit unsigned mono, mostly 8000 Hz). This writes
wav/NNN.wav and index.html (a player per sample, its length and rate, and every LIFE script that
plays it, with the objects and rooms that run that script). Original game data: keep it local.
  python Generated/Sounds/extract_samples.py"""
import html, re, struct, sys, wave
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "Patcher")]
import aitd_life as L, aitd_objets as O, gamedata


def voc_pcm(data: bytes) -> tuple[int, bytes]:
    """(sample rate, 8-bit unsigned PCM) from a VOC file: type-1 sound blocks (and type-2
    continuations), codec 0 only."""
    p = struct.unpack_from("<H", data, 20)[0]
    rate, out = 8000, bytearray()
    while p < len(data) and data[p] != 0:
        kind = data[p]
        size = data[p + 1] | data[p + 2] << 8 | data[p + 3] << 16
        body = data[p + 4:p + 4 + size]
        if kind == 1:
            rate = 1000000 // (256 - body[0])
            if body[1] != 0:
                raise ValueError(f"codec {body[1]} not supported")
            out += body[2:]
        elif kind == 2:
            out += body
        p += 4 + size
    return rate, bytes(out)


def usage() -> dict[int, list[str]]:
    lives = gamedata.pak_entries("LISTLIFE.PAK")
    objs = O.load(gamedata.source_dir() / "OBJETS.ITD")
    runs = {}
    for i, o in enumerate(objs):
        for k in ("life", "found_life", "floor_life"):
            if o[k] >= 0:
                where = f"F{o['stage']}:R{o['room']}" if o["stage"] >= 0 else "carried/off-world"
                runs.setdefault(o[k], []).append(f"OBJ {i} ({where})")
    used = {}
    for n, d in enumerate(lives):
        for line in L.format_script(L.decode(d)).splitlines():
            for m in re.finditer(r"\b(sound|anim_sound|rep_sound) #(\d+)", line):
                who = ", ".join(sorted(set(runs.get(n, ["set by another script"]))))
                used.setdefault(int(m.group(2)), set()).add(f"LIFE {n} {m.group(1)} — {who}")
    return {k: sorted(v) for k, v in used.items()}


def main():
    samples = gamedata.pak_entries("LISTSAMP.PAK")
    (HERE / "wav").mkdir(exist_ok=True)
    used = usage()
    rows = []
    for n, d in enumerate(samples):
        rate, pcm = voc_pcm(d)
        with wave.open(str(HERE / "wav" / f"{n:03d}.wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(1); w.setframerate(rate); w.writeframes(pcm)
        where = "".join(f"<li>{html.escape(u)}</li>" for u in used.get(n, [])) or "<li><i>no script plays it</i></li>"
        rows.append(f'<tr><td>{n}</td><td><audio controls preload="none" src="wav/{n:03d}.wav"></audio></td>'
                    f"<td>{len(pcm) / rate:.2f} s</td><td>{rate} Hz</td><td><ul>{where}</ul></td></tr>")
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>AITD sound effects</title>
<style>body{{font-family:system-ui,sans-serif;margin:16px;background:#fafafa;color:#222}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #ddd;padding:6px;vertical-align:top;text-align:left}}
ul{{margin:0;padding-left:18px;font-size:13px}}audio{{height:32px}}
@media (prefers-color-scheme:dark){{body{{background:#1b1b1b;color:#ddd}}td,th{{border-color:#333}}}}</style></head>
<body><h1>AITD sound effects ({len(samples)} samples, LISTSAMP.PAK)</h1>
<p>Number = the sample index scripts use (<code>sound #N</code>). "Where" lists the LIFE scripts that play it and the objects that run them.</p>
<table><tr><th>#</th><th>Play</th><th>Length</th><th>Rate</th><th>Where</th></tr>{''.join(rows)}</table></body></html>"""
    (HERE / "index.html").write_text(page, encoding="utf-8")
    print(f"{len(samples)} samples -> {HERE / 'wav'}; page {HERE / 'index.html'}")


if __name__ == "__main__":
    main()
