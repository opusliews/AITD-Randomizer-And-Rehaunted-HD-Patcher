"""Build the ready-to-open player exports in out/:
  edward_player.glb  - Edward (LISTBODY 12) + his 35 player animations (LISTANIM)
  emily_player.glb   - Emily  (LISTBOD2 12) + her versions (LISTANI2)
  edward_rifle.glb   - Edward holding the rifle (LISTBODY 30, 20 groups: prop bones g17-g19) + same animations
Names: anim_NNN_<role>; roles from the LIFE anim_move sets (stand, walk, run, stop, back, turn R, turn L).
"""
from export_gltf import export
from verify_gltf import main as verify

PLAYER = [4, 254, 255, 256, 257, 258, 259, 260, 271, 295, 296, 2, 3, 5, 8, 10, 13, 26, 27, 28, 29, 30, 31,
          32, 33, 37, 38, 39, 40, 41, 68, 126, 127, 264, 273]
ROLE = {4: "idle", 254: "walk", 255: "run", 256: "walk_back", 257: "turn_right", 258: "turn_left",
        259: "walk_alt1", 260: "walk_alt2", 271: "walk_alt3", 295: "walk_alt4", 296: "run_alt4"}
NAMES = {a: f"anim_{a:03d}" + (f"_{ROLE[a]}" if a in ROLE else "") for a in PLAYER}

for out, body, bp, ap in (("out/edward_player.glb", 12, "LISTBODY.PAK", "LISTANIM.PAK"),
                          ("out/emily_player.glb", 12, "LISTBOD2.PAK", "LISTANI2.PAK"),
                          ("out/edward_rifle.glb", 30, "LISTBODY.PAK", "LISTANIM.PAK")):
    export(body, PLAYER, out, bp, ap, NAMES)
    print("==", out); verify(out)
