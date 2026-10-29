"""Install / unpatch a generated seed in a game folder (work-order step 4, part 3).

  python install.py detect  GAME_DIR
  python install.py apply   SEED_DIR GAME_DIR [--force] [--fix-config] [--edition EXE]
                                              [--game-data DIR] [--force-data]
  python install.py unpatch GAME_DIR
  python install.py find-data [DIR]

GAME_DIR is the folder holding the game data files (a GOG/Steam install's
INDARK folder, a ReHaunted folder, a FITD folder). One folder can hold several
programs: ReHaunted deploys itself into the GOG/Steam INDARK folder and
replaces DOSBOX\\DOSBox.exe with a stub (Research/ReHauntedDataHandling.md);
vanilla INDARK.EXE and ReHaunted Tatou.exe then read the same PAK files.

detect   lists the programs found (by known SHA-256, else by name) and their
         state: vanilla exe pristine/patched, ReHaunted build, FITD, DOSBox
         launcher pristine or replaced, native LIFE scripts setting, data
         files present, an installed seed.
apply    copies the seed's patch files (SEED_DIR/patchset/*.PAK, *.ITD) into
         GAME_DIR after backing up every file it replaces into
         GAME_DIR/AITD_Randomizer_Backup, and writes the marker
         GAME_DIR/AITD_Randomizer.json (seed, files, hashes before and after).
         Refuses: a folder inside OriginalGame; no ITD_RESS.PAK (ReHaunted
         would then copy the original data over the seed); a seed already
         installed; a file to replace that is not the vanilla file (--force
         overrides); ReHaunted with native LIFE scripts enabled (--fix-config
         sets it to false, backing up the config).
         --edition EXE also replaces the folder's ReHaunted Tatou.exe with the
         AITD Randomizer edition EXE (backed up like the data files). The
         edition is only installed over an existing ReHaunted install; EXE must
         be a known edition build (EDITION below).
         A ReHaunted folder without game data (ReHaunted plays on data embedded
         in its exe; the edition has none): the original data files are found
         like ReHaunted does it (gameDataCopy.cpp: Steam, then GOG, then a CD;
         or --game-data DIR), checked against the known GOG hashes (refused if
         any differs or is missing, unless --force-data), and copied in; the
         marker lists them so unpatch removes exactly those. The found install
         is only read. With --edition, gamedata.steamless = true is set in
         aitd_remaster.cfg / aitd_remaster_hd.cfg (2.4 / 2.3 names; backed up,
         or created and later removed), so the
         game never copies data over the seed or deploys itself into the
         player's Steam/GOG folder.
unpatch  restores every backed-up file, checks each restored file against its
         recorded vanilla hash, removes the game data files apply copied in (if
         unchanged), then removes the marker and the backup.
find-data  runs the game-data search (and checks DIR, if given) and reports.

Saves belong to their seed: a save from another seed or from vanilla will
break the game (agreed rule); apply and unpatch print this warning.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = HERE.parent
ROOT = GEN.parent
SRC = GEN / "ResearchRun" / "SourceCopy"
MARKER = "AITD_Randomizer.json"
CFG_NAMES = ("aitd_remaster.cfg", "aitd_remaster_hd.cfg")   # ReHaunted 2.4+, 2.3 (configRemaster.cpp)
BACKUP = "AITD_Randomizer_Backup"
SAVE_WARNING = ("WARNING: saves belong to their seed. Loading a save made with another seed, or "
                "with the unpatched game, will break the game. Start a New Game.")

KNOWN = {
    "INDARK.EXE": {
        "2f2c0c27aa84fc10958ac10ab77a804cc500b531fac14bab7d7613064a874df1": "vanilla GOG INDARK.EXE (pristine)",
        "89b24e8bb24a6deafc81fa6612730770fc63c6ee2235bf38968b2ccf24a086e6": "vanilla, patched --max-objects 400",
        "f8ea456c4eca98d273f53f7ce09109b363a5a2dcd97cd1b6649a1fe55a05c1ed":
            "vanilla, patched --max-objects 400 --items-dont-block-push",
        "d8b58e42ee61b581010cf5f778063941831e044c303af967a61fc633d3ae38a1":
            "vanilla, patched --max-objects 400 --items-dont-block-push --search-hint",
    },
    "DOSBOX/DOSBox.exe": {
        "8a7a7fedd222bf985b51191000557f9ee2ffb033be02c6c59594dbbec013cd41": "GOG DOSBox 0.74 (pristine launcher)",
    },
    "FITD.exe": {
        "277ecfb71c9443df5fda7c4c7c6ffae3fdeb7b2e55d0f75f66c305c9b468f70b": "FITD build of Dec 2004 bundled with GOG (not started by the GOG launcher)",
    },
    "Tatou.exe": {
        "7d758734190b3eebf6c4053cc9bda7097a6e0c32f41fb9b9c4c01ebc98827c72": "ReHaunted (project build 7D758734)",
        "f90bf9522e41222e536c7968441b663df31de89cc722f61bda1fe7f61dfd8b79":
            "ReHaunted 2.4.0.1008, official release (built Aug 9 2026)",
    },
}


# AITD Randomizer edition of ReHaunted (Research/ReHauntedDataHandling.md): builds the
# installer accepts for --edition. Newest last.
EDITION = {
    "9046dd45fdb805739711d4257564cfc4624654181d5df2baf0c6c0e6d6b86075": "edition 9046DD45 (no capture)",
    "b0c5f4d0aa5c0584855e7ce5910a0551e1be1f16cb9340d0b67f9599ec2a7881": "edition B0C5F4D0 (F7 capture)",
    "08cb9f2b996b8a5743a3d86ab788e6e3eeb89ed4f89df382fa75242c145adbf9": "edition 08CB9F2B (ReHaunted 2.4 base, F7 capture)",
    "914e2c9a156459ecdb381020d165cd22ce07f5d230349c3cac1d249fe536f7ae": "edition 914E2C9A (ReHaunted 2.4 base, F7 capture, native scripts off, steamless)",
    "b627b02a9c60435a6aba778590de3bdb442a28de7e3c9aff3609ddb2650d150f": "edition B627B02A (ReHaunted 2.4 base, F7 capture, native scripts off, steamless, chime fix)",
    "11d537de49adc1b574b8aaa7296c0e0d95362df25e420ae0edfe5f05f1104608": "edition 11D537DE (ReHaunted 2.4 base, F7 capture, native scripts off, steamless, chime fix, positional loops)",
    "983bea810258577b7f067dd4b876846a15097680de71a507e1b9b151408ee333": "edition 983BEA81 (ReHaunted 2.4 base, F7 capture, native scripts off, steamless, chime fix, positional loops, exe-folder working dir)",
    "c8c085cb493cbd2605e7c39d806dcaa18757b9189d5d2a9fbf8df05348a2a162": "edition C8C085CB (ReHaunted 2.4 base, F7 capture, native scripts off, steamless, chime fix, positional loops, exe-folder working dir, authentic darkness)",
    "e99ce47c595c0c5826b41df406ac13ec6392ddd17feaa4eaf2fd25c29815196f": "edition E99CE47C (ReHaunted 2.4 base, F7 capture, native scripts off, steamless, chime fix, positional loops, exe-folder working dir, authentic darkness, lamp glow fix)",
    "3563e60838761d89f5fe51ee9dadaa5cf798b9fe81b31a76c93c5f1031b72b15": "edition 3563E608 (ReHaunted 2.4 base, F7 capture, native scripts off, steamless, chime fix, positional loops, exe-folder working dir, authentic darkness, lamp glow fix + placed/thrown lamp glow)",
    "8a65349c06d8f3cf221e4518a6fdf6fbd365d661bbfb489bc82ebf7293e09845": "edition 8A65349C (ReHaunted 2.4 base, F7 capture, native scripts off, steamless, chime fix, positional loops, exe-folder working dir, authentic darkness, lamp glow fixes)",
    "cc9eaa8e39795f25a58d09fd23fe5dce659c8e1f315fd3e1f10a05dd62a9732d": "edition CC9EAA8E (as 8A65349C + blood/smoke effect heap overrun fix)",
    "b5e3e559335933bc716d6ecf1dafd609c983efe3722217fc24213c25d59a1048": "edition B5E3E559 (as CC9EAA8E; the test exes' noclip code is compiled in but always off)",
    "f9786e11a1240139413b652f672a47084d1cdd64435c214a7544dd475f895f4f": "edition F9786E11 (as B5E3E559; positional looping sounds fade twice as fast: 30 % at 4750)",
    "20915541d99080401381150d7b22e63a3895585e79ea01eae76c15b55217c630": "edition 20915541 (as F9786E11; positional looping sounds fade to silence at 4750)",
    "56348d40d4cb5678db31a3ba1b88ee97ad59d8981cf02c8702821f7ce2a0751e": "edition 56348D40 (as 20915541; looping sounds fade from 1500 to silence at 14500)",
    "0ebe0066f27e7fcfd248a0b79c280b0c74a500bcd245e9c51ad33df30f61b8de": "edition 0EBE0066 (as 56348D40; looping sounds silent at 9062.5)",
    "a1a8a8b7d6748257d2f1c72739b625291c95d1649285de32a32721f65da4c17c": "edition A1A8A8B7 (as 0EBE0066; drop glow drawn at 30 %, 20 % over HD backgrounds)",
    "10d6db227a52dab7e5ddfe82acbf9740ccba13b58f0549988bc64672df25132f": "edition 10D6DB22 (as A1A8A8B7; no HD atlas over the drop glow)",
    "3526d627ce2395653cf740dd7911eed30d164549e328c242e89a1e360dc2eeb7": "edition 3526D627 (as 10D6DB22; relinked 2026-10-20, the TatouHd changes are compiled out)",
    "a669a29c5d5e80077e9edab324f9168721642febbaea4908ddc7269ea870cf67": "edition A669A29C (as 3526D627; SoLoud mixes at the SDL stream rate, fixes slow audio on 48 kHz devices)",
    "b6b70f3c8972d4d5345ff0bd27473b2c0929087fd2f65b31754075c2bd6b455a": "edition B6B70F3C (as A669A29C; no player shadow after the corridor floor collapses)",
    "6b7370e2c087e1e588fcb1f72579dddcb06706ec79870c2db743cce420b21894": "edition 6B7370E2 (as B6B70F3C; Smoking Room smoke on the original 11 s cycle, with the cough damage)",
    "b07958df51611f9d3afbe3786ddcecbdf32fdecfba84969f97601a1a0520fb27": "edition B07958DF (as 6B7370E2; the smoke cloud is drawn as in the original: 20 grey transparent puffs spreading outward)",
    "10588873babf037689f8c5d1db0dc1ab799b89523ddc3d44271b797c8ef63c26": "edition 10588873 (as B07958DF; fuller smoke cloud: puffs spread up to 1200 higher, some turn faster, some darker)",
    "f8ef8845b8889784a94d47d3b886c1038fb8e5ec2568912bb729e076178e0f90": "edition F8EF8845 (as 10588873; backgrounds follow the HD backgrounds setting at once)",
    "96a775d6bc1510eca00578d692d4031e6e528df057502b80426e00a046a525d0": "edition 96A775D6 (as F8EF8845; smoke puffs rise to their extra height from the ashtray)",
    "e7020086259c020a2a57260528fd708ed9d5fce9e130d49a3df4ff04dd6dbec3": "edition E7020086 (as 96A775D6; optional keyboard + mouse controls, read from the install record)",
    "c2c652869b14f616696b4fdfe8ac37bdd6810cb103f0f8477c6f28ae55ff9323": "edition C2C65286 (as E7020086; the controls keep the cursor hidden through ImGui)",
    "72c2eebc8af6530973c5d6c679749c43174b5440b1a064071aa4570b2ad952a1": "edition 72C2EEBC (as C2C65286; controls: C walks up to an open door and closes it)",
    "8917efb9ae094201193e4d718538633013cab9f436a57c12e57e7f3776bbef7d": "edition 8917EFB9 (as 72C2EEBC; controls: Q also while walking, he walks on after the turn)",
    "5e9cab2adcf10bd3e3ad1b1dfd6185b53628f0d0f9fcd76676211bbd1dd4c1c2": "edition 5E9CAB2A (as 8917EFB9; plays the same; only the debug option Enable native LIFE scripts, always off in the edition, now gets the mouse fire/attack direction)",
    "37171518e6afb833b99b47fd250a409f430c8debc826aeead7553c516c2e74b0": "edition 37171518 (as 5E9CAB2A; controls: hold left to fire guns and bow as soon as they are up, no double-click fullscreen)",
    "55f4bfc0da17591b5593390edd9e9343490037e8843104fc56bc40dc7065d68a": "edition 55F4BFC0 (as 37171518; optional maintain aspect ratio: 16:10 with black bars, read from the install record)",
    "6020408a7492936f99a3a7261d46c864121d455262bbdff5699c252a0f67b0aa": "edition 6020408A (as 55F4BFC0; model texture atlases capped at 4096: no freeze on showing the arrows; F8 inspector cursor with the controls, inspector-only)",
    "d2c69cac948ca00890aa5235f4e4a7be8a570764a45f435dbbc1ba30c7a77a59": "edition D2C69CAC (as 6020408A; an oversized atlas in atlases.hda is skipped from its PNG header, without reading the image)",
    "1f5cf668893f0a562c062e969084ca3c28ffa374ff3422f3257eaa3cd2243cc1": "edition 1F5CF668 (as D2C69CAC; the worm's chase turns its wall collision back on (LIFE 460 test_col 1), so it stops after a cellar-first visit)",
    "3e5f2b7ca9b6722b5925f480dab22994d7c441d27e0e031cc6482dbcf79d41d0": "edition 3E5F2B7C (as 1F5CF668; takes a seed's already patched LIFE 522 as it is: every seed now carries the cellar/tunnel fixes)",
    "91dce3cc636f2290c43393afedf5b8435f8934a299129c092fb3671cac7cc148": "edition 91DCE3CC (as 3E5F2B7C; the cave water: models are cut at the waterline as in the original, no screen shake on entering the caves)",
    "d49747b627b32b2d4676759678ae20eea983bf69ca8143d25d6a4b334f16196b": "edition D49747B6 (as 91DCE3CC; the ending starts on the doorstep shot (CAMERA07_005) as in the original: the stuck-in-wall warp moves only the player)",
    "5e4aa4509fdea324c7a851d5bdf483563887e5bebd235b5b9ceab56e40a176ea": "edition 5E4AA450 (as D49747B6; save slot thumbnails change with the selected slot in HD mode)",
    "926d37bf807b9ed8ce3c26017e2f153a692a86c70ae621210f3197b619962d79": "edition 926D37BF (as 5E4AA450; the crimson drop glow (colour 0x51) is drawn faint and see-through like the grey one)",
    "b70c8a998f406c24d6b4683355c0db15bc5897b588af77025d356f676b266bc8": "edition B70C8A99 (as 926D37BF; the drop glow is told by its model, 274, so its colour can be 0x50 like the Talisman's)",
}
KNOWN["Tatou.exe"].update({h: "AITD Randomizer " + v for h, v in EDITION.items()})


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


VANILLA = {   # SHA-256 of the original GOG INDARK data files (ResearchRun/SourceCopy, 2026-10-15)
    "CAMERA00.PAK": "3c355ddbc928740f339e963e797be81071b027a2f23cfc933ad7edb3c7aa9b3e",
    "CAMERA01.PAK": "94a320a81cb21d658cb5f52da4372e5a11e8bd59b6805129b5ac0564e7d46672",
    "CAMERA02.PAK": "6656034c2c98c16d4b657947390f36104a67295bdb4bb8ec16535795f7c33661",
    "CAMERA03.PAK": "add45a46197b4cd46b245253a48a304d6e7322855fff07bf8708d3c4fdb6f540",
    "CAMERA04.PAK": "b60d03f76ff9f5712e15499a457560290d23a2213f3927768483a4f1b42cb49d",
    "CAMERA05.PAK": "80ee5d0c6c0236bf6f545a0fa10f6cbd13046ffe773d70e8d661353177e9e61e",
    "CAMERA06.PAK": "5402137f3c7fa05cebd0e3f7a7d864ff414b28ac2be5add8e9ed88553d936ebb",
    "CAMERA07.PAK": "04b32a49bbfb8d1f4b1221f26cb3db3727b778ecabeb278863c4d73890364575",
    "DEFINES.ITD": "decb15c7dcec89a5b9ee238da554211d4f882b25427cc02970e50c233c5b1739",
    "DEUTSCH.PAK": "5137e2192d8d59b1e2898e17d80f3decfac9de14cd6e4392fddbdba170f1c1d3",
    "ENDSEQ.PAK": "0aab1a9acbbd6567afe20db19ed92782bf93ff6652db6cc845e6f6dd910481fd",
    "ENGLISH.PAK": "444c1398c8ce6183de9a4ecff15fed039526fd780e62d9af02c33b7e89108d23",
    "ESPAGNOL.PAK": "4881e7b809948eb73c379261889badcd663a6a8774ec1c6eb36e6dbbe1f8cb83",
    "ETAGE00.PAK": "14eddeb2b5158740d324104e50694225f237b33f30f9cbeadba166467ec48dab",
    "ETAGE01.PAK": "4865de454a24f224d2de949b9c40beaf543ccc76ad4e7f8a8f9b84461e85aa87",
    "ETAGE02.PAK": "315768a84331dad60acc992b7848a76bedadbca1ecbbcb5849afd6689c292fbf",
    "ETAGE03.PAK": "c8155e6cc5c562d08fafacbf9d9400140acae2070867f9ee201a56faf3d4a518",
    "ETAGE04.PAK": "13253695d0710cbc24298feea7d45eed2bd5991af5a9f1b729d467d80fb92bf8",
    "ETAGE05.PAK": "3899cc8472db311f62d5aec41a7d4391d87f21445b04f8b1aadddc77f50d4338",
    "ETAGE06.PAK": "e4550f6422fc6dc87fb836d2d0600ae091204a16b48488b72cf019ff72905f70",
    "ETAGE07.PAK": "4a7473638b3d8adffd7be593d92331b78184e91cf477349e94c6f861e79f0132",
    "FRANCAIS.PAK": "19da3b894681a69da3de6aaa56a9db5ee017058a44641381b160e295da7aac4c",
    "ITALIANO.PAK": "36f18710952bbb72adb309f2fee32b389e15f2638fe803d05e3cad56f478ed6e",
    "ITD_RESS.PAK": "55ab67ae35d41351750af081addc7c54c8997484e22b0d69f018f34259dcc486",
    "LISTANI2.PAK": "6c47a81f0983aa8216cf20b177a279a32d4468afddbe831638c02378843c2642",
    "LISTANIM.PAK": "7c069662d6bca097221634e35f99ab05277f96377da58bcc09cf060f09cebc01",
    "LISTBOD2.PAK": "03570976c4001abf868730038943fc68e9aa6cb310045467d58776a529d52737",
    "LISTBODY.PAK": "05eb047fc09f311b8c896742364d1b831bf0b5d9c88d6c3e81dc182281bf8205",
    "LISTLIFE.PAK": "99d7d62490766c16d0df3e5d4624b74257300b8c45a70ab29cc1b474ca7deb1b",
    "LISTMUS.PAK": "ccd2c69d6a73478193e6bbcce863115de7775301bd859b472a6cdbca68d48add",
    "LISTSAMP.PAK": "0af5ab5eeabc62b1fb97e5db0508c63f58bda7a8289b3b8c08d4ae0915e15bb5",
    "LISTTRAK.PAK": "b7fa504b336ff086338b9f158e7ae688b0f354ed1e3c3ef2b6b7f2ac39f76400",
    "OBJETS.ITD": "510d1943430ded9b379755fbc95dcc6c6e0a4b69569e407bc53c7d93d0d09bb7",
    "PRESENT.PAK": "1ccf1c88b21170798029659a2714a78d7c6a933cb6b13f2e278f4e385f524ec0",
    "PRIORITY.ITD": "3eb8fbafdc910c5e4c57324b0b6136cf5e6ac509fcef1703edcc6793f928a6ea",
    "USA.PAK": "88aa5ee87a2ccfe0a9fcbe01bd1866182c1cf5e886628deeef10432a9b37fdc3",
    "VARS.ITD": "b963097a5d603fa5427cddec342aeff614b215b617e47c6c070e04cd3574590a",
}


def vanilla_hashes() -> dict[str, str]:
    """Built in, so install.py runs on its own (no project folders, no game data needed).
    Inside the project it is cross-checked against the source copy."""
    if SRC.is_dir():
        disk = {p.name.upper(): sha(p) for p in SRC.iterdir() if p.suffix.upper() in (".PAK", ".ITD")}
        if disk != VANILLA:
            raise SystemExit("built-in vanilla hashes differ from ResearchRun/SourceCopy")
    return dict(VANILLA)


# ---- vanilla INDARK.EXE object-table patch (from Generated/Patcher/vanilla_exe.py) ------------
# A seed with more than 300 objects (More Locked Doors keys) needs the original DOS exe's
# object table raised; tested in DOSBox-X (T1-T3, VanillaExe_Ghidra.md). Each location is
# checked against its original bytes; the result must be the known patched build.
GOG_INDARK = "2f2c0c27aa84fc10958ac10ab77a804cc500b531fac14bab7d7613064a874df1"
INDARK_400 = "89b24e8bb24a6deafc81fa6612730770fc63c6ee2235bf38968b2ccf24a086e6"
INDARK_CLASSIC = "f8ea456c4eca98d273f53f7ce09109b363a5a2dcd97cd1b6649a1fe55a05c1ed"   # 400 + push fix (T4)
INDARK_CLASSIC_HINT = "d8b58e42ee61b581010cf5f778063941831e044c303af967a61fc633d3ae38a1"  # + search hint (T7)
# + keyboard/mouse controls (vanilla_exe.py --controls; Research/VanillaControls_Design.md)
INDARK_CLASSIC_CTRL = "1d119163652f7a9ca2832873bb1d5a875fe763ccc27ab75bd05c04a3aa0f2015"
INDARK_CLASSIC_HINT_CTRL = "f5b5ec2f9e726a7b1c8d58f678783ce7411603282806e1f8e07e46e11de706c0"
INDARK_CLASSIC_FOR = {(False, False): INDARK_CLASSIC, (True, False): INDARK_CLASSIC_HINT,
                      (False, True): INDARK_CLASSIC_CTRL, (True, True): INDARK_CLASSIC_HINT_CTRL}
INDARK_RAISED = {INDARK_400, *INDARK_CLASSIC_FOR.values()}
INDARK_OBJECT_LIMIT_400 = [            # (file offset, original, patched): table size, save block 6, loop
    (0x4AC1, "f03c", "4051"),          # farmalloc 300*52 -> 400*52 = 20800 = 0x5140
    (0x1B6DE, "f03c0000", "40510000"),  # save-block 6 size
    (0xA30C, "81fa2c01", "3b1652ab"),  # cmp dx,300 -> cmp dx,[ab52] (real object count)
]


# Push fix (vanilla_exe.py --items-dont-block-push, test T4): takable items no longer block
# pushing furniture. 1d8a:017f CheckObjectCol, file offset = 0xF4A0 + segment offset.
INDARK_ITEMS_DONT_BLOCK_PUSH = [
    (0xF4A0 + 0x1B8, "8b46fe", "e98d00"),
    (0xF4A0 + 0x246, "8bc6d1e0c41ef98303d826897f7e4683fe037507b803005f5ec9cb",
     "ebcb8b46063b06f783740826f7470480007508" "8b46fee95cff9090"),
]


def _patched(data: bytearray, patches) -> bool:
    for off, orig, new in patches:
        if data[off:off + len(orig) // 2].hex() != orig:
            return False
    for off, orig, new in patches:
        data[off:off + len(new) // 2] = bytes.fromhex(new)
    return True


def indark_classic(exe: Path, hints: bool = False, controls: bool = False) -> bytes | None:
    """Every Classic install (user decision 2026-10-16): the 400-object table and the push fix;
    with hints (app option "Hints On", 2026-10-17) also the search hint, the outlined "?" near
    searchable zones (vanilla_exe.py --search-hint, test T7); with controls (app option "Keyboard
    and mouse controls", 2026-10-23) the controls segment after it (vanilla_exe.py --controls).
    From the pristine GOG exe, the 400-only build, the Classic build, or (adding the controls)
    the Classic hint build; None if the bytes or the result are not the known ones (the result
    must be INDARK_CLASSIC_FOR[hints, controls])."""
    data = bytearray(exe.read_bytes())
    h = hashlib.sha256(data).hexdigest()
    if h == GOG_INDARK and not _patched(data, INDARK_OBJECT_LIMIT_400):
        return None
    add_hint = hints
    if h in (GOG_INDARK, INDARK_400):
        if not _patched(data, INDARK_ITEMS_DONT_BLOCK_PUSH):
            return None
    elif h == INDARK_CLASSIC_HINT and hints and controls:
        add_hint = False                  # the hint segment is already there; the controls follow it
    elif h != INDARK_CLASSIC:
        return None
    if add_hint or controls:
        sys.path.insert(0, str(GEN / "Patcher"))
        import vanilla_exe
        from contextlib import redirect_stdout
        import io
        with redirect_stdout(io.StringIO()):
            if add_hint and not vanilla_exe.add_search_hint(data):
                return None
            if controls and not vanilla_exe.add_controls(data):
                return None
    want = INDARK_CLASSIC_FOR[bool(hints), bool(controls)]
    return bytes(data) if hashlib.sha256(data).hexdigest() == want else None


def objets_count(path: Path) -> int:
    return int.from_bytes(path.read_bytes()[:2], "little")


# ---- original game data: ReHaunted's own search (FitdLib/gameDataCopy.cpp), ported -------
STEAM_APP_ID = 548090
GOG_GAME_ID = "1207660923"
SENTINEL = "ITD_RESS.PAK"
GOG_COMMON = [r"C:\GOG Games\Alone in the Dark",
              r"C:\Program Files (x86)\GOG Galaxy\Games\Alone in the Dark",
              r"C:\Program Files\GOG Galaxy\Games\Alone in the Dark",
              r"D:\GOG Games\Alone in the Dark"]
NO_DATA = ("The original Alone in the Dark game files are needed, and none were found (Steam, GOG or "
           "CD). Install the game from GOG or Steam, or choose the folder that contains ITD_RESS.PAK "
           "(--game-data).")


def _reg_value(key: str, name: str) -> str | None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
            v, t = winreg.QueryValueEx(k, name)
            return v if t == winreg.REG_SZ and v else None
    except (OSError, ImportError):
        return None


def _with_sentinel(*cands: Path) -> Path | None:
    for c in cands:
        if c.is_dir() and find(c, SENTINEL):
            return c
    return None


def find_steam_data() -> Path | None:
    """Steam registry InstallPath -> steamapps/libraryfolders.vdf "path" entries ->
    appmanifest_548090.acf "installdir" -> steamapps/common/<dir>/INDARK, else its root."""
    import re
    steam = (_reg_value(r"SOFTWARE\Valve\Steam", "InstallPath") or
             _reg_value(r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"))
    if not steam:
        return None
    try:
        vdf = (Path(steam) / "steamapps" / "libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for lib in re.findall(r'"path"\s*"([^"]*)"', vdf)[:16]:
        lib = Path(lib.replace("\\\\", "\\"))
        try:
            acf = (lib / "steamapps" / f"appmanifest_{STEAM_APP_ID}.acf").read_text(
                encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(r'"installdir"\s*"([^"]*)"', acf)
        if m:
            base = lib / "steamapps" / "common" / m.group(1)
            hit = _with_sentinel(base / "INDARK", base)
            if hit:
                return hit
    return None


def find_gog_data() -> Path | None:
    """GOG registry Games/1207660923 PATH -> INDARK, else its root; then the common folders."""
    for key in (rf"SOFTWARE\GOG.com\Games\{GOG_GAME_ID}", rf"SOFTWARE\WOW6432Node\GOG.com\Games\{GOG_GAME_ID}"):
        path = _reg_value(key, "PATH")
        if path:
            hit = _with_sentinel(Path(path) / "INDARK", Path(path))
            if hit:
                return hit
    for c in GOG_COMMON:
        hit = _with_sentinel(Path(c) / "INDARK", Path(c))
        if hit:
            return hit
    return None


def find_cd_data() -> Path | None:
    """CD/DVD drives D: to Z: -> X:/INDARK."""
    try:
        import ctypes
        get_type = ctypes.windll.kernel32.GetDriveTypeW
    except (ImportError, AttributeError):
        return None
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        if get_type(f"{letter}:\\") == 5:                      # DRIVE_CDROM
            hit = _with_sentinel(Path(f"{letter}:\\INDARK"))
            if hit:
                return hit
    return None


def search_game_data() -> list[tuple[str, Path]]:
    """Every source found, in ReHaunted's order (it uses the first)."""
    out = []
    for how, fn in (("Steam", find_steam_data), ("GOG", find_gog_data), ("CD", find_cd_data)):
        hit = fn()
        if hit:
            out.append((how, hit))
    return out


def check_game_data(src: Path) -> tuple[list[str], list[str]]:
    """(missing, different) against the known original GOG files."""
    missing, different = [], []
    for name, h in VANILLA.items():
        p = find(src, name)
        if p is None:
            missing.append(name)
        elif sha(p) != h:
            different.append(name)
    return missing, different


def find(game: Path, rel: str) -> Path | None:
    """Case-insensitive lookup of rel (may go one level up for DOSBOX)."""
    parts = rel.split("/")
    base = game.parent if parts[0].upper() == "DOSBOX" else game
    cur = base
    for part in parts:
        if not cur.is_dir():
            return None
        hit = next((c for c in cur.iterdir() if c.name.upper() == part.upper()), None)
        if hit is None:
            return None
        cur = hit
    return cur


def detect(game: Path) -> dict:
    info = {"folder": str(game), "programs": [], "data_files": 0, "sentinel": False,
            "native_life_scripts": None, "installed_seed": None}
    for rel, table in KNOWN.items():
        p = find(game, rel)
        if p and p.is_file():
            h = sha(p)
            default = ("replaced launcher (likely the ReHaunted DOSBox stub, which starts ReHaunted)"
                       if rel.startswith("DOSBOX") else f"unrecognised {rel} (unknown build)")
            info["programs"].append({"file": rel, "sha256": h, "identified_as": table.get(h, default)})
    for p in game.iterdir():
        if p.suffix.upper() == ".EXE" and p.name.upper().startswith("FITD") and p.name.upper() != "FITD.EXE":
            info["programs"].append({"file": p.name, "sha256": sha(p), "identified_as": "FITD (by name)"})
    van = vanilla_hashes()
    info["data_files"] = sum(1 for p in game.iterdir() if p.name.upper() in van)
    info["sentinel"] = find(game, "ITD_RESS.PAK") is not None
    info["configs"] = []
    for name in CFG_NAMES:
        cfg = find(game, name)
        if not cfg:
            continue
        info["configs"].append(cfg.name)
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("debug.enableNativeLifeScripts"):
                on = line.split("=", 1)[1].strip().lower() in ("true", "1")
                info["native_life_scripts"] = bool(info["native_life_scripts"]) or on
    if (game / MARKER).exists():
        info["installed_seed"] = json.loads((game / MARKER).read_text(encoding="utf-8"))["seed"]
    return info


def refuse(msg: str) -> int:
    print("REFUSED: " + msg)
    return 1


def apply(seed_dir: Path, game: Path, force: bool, fix_config: bool, edition: Path | None = None,
          game_data: Path | None = None, force_data: bool = False, hints: bool = False,
          controls: bool = False, keep_aspect: bool = False) -> int:
    game = game.resolve()
    if (ROOT / "OriginalGame").resolve() in [game, *game.parents]:
        return refuse("the folder is inside OriginalGame, which is read-only")
    info = detect(game)
    if info["installed_seed"] is not None:
        return refuse(f"seed {info['installed_seed']} is already installed; unpatch first")
    is_rehaunted = any(p["file"] == "Tatou.exe" for p in info["programs"])
    data_src = None
    if not info["sentinel"]:
        if not is_rehaunted:
            return refuse("no ITD_RESS.PAK here: not a game folder (choose the folder holding the game's "
                          ".PAK files, or a ReHaunted folder)")
        if game_data is not None:
            data_src, how = game_data.resolve(), "chosen folder"
            if not find(data_src, SENTINEL):
                return refuse(f"no {SENTINEL} in {data_src}: " + NO_DATA)
        else:
            found = search_game_data()
            if not found:
                return refuse(NO_DATA)
            how, data_src = found[0]
        missing, different = check_game_data(data_src)
        if (missing or different) and not force_data:
            return refuse(f"the game files in {data_src} ({how}) are not the known original GOG files"
                          + (f"; missing: {', '.join(missing)}" if missing else "")
                          + (f"; different: {', '.join(different)}" if different else "")
                          + ". Seeds are built from the GOG release; --force-data to use them anyway")
        print(f"game data: {data_src} ({how}), {len(VANILLA) - len(missing)} file(s) to copy")
    if is_rehaunted and info["native_life_scripts"] and edition is None:   # the edition forces them off
        if not fix_config:
            return refuse("ReHaunted has debug.enableNativeLifeScripts = true, which would bypass the "
                          "patched scripts; rerun with --fix-config")
    files = sorted(p for p in (seed_dir / "patchset").iterdir() if p.suffix.upper() in (".PAK", ".ITD"))
    if not files:
        return refuse(f"no patch files in {seed_dir / 'patchset'}")
    tatou = find(game, "Tatou.exe")
    if edition is not None:
        edition = edition.resolve()
        if not edition.is_file():
            return refuse(f"edition exe not found: {edition}")
        if sha(edition) not in EDITION:
            return refuse(f"{edition.name} is not a known AITD Randomizer edition build "
                          f"(sha256 {sha(edition)[:16]})")
        if tatou is None:
            return refuse("--edition installs only over an existing ReHaunted install, and this folder "
                          "has no Tatou.exe")
        if sha(tatou) in EDITION:
            return refuse("Tatou.exe here is already a randomizer edition build; unpatch first or "
                          "reinstall the official ReHaunted")
    elif is_rehaunted:
        print("note: ReHaunted found. Without --edition, the stock Tatou.exe runs the seed "
              "(no F7 capture, no randomizer engine fixes)")
    # every check that can refuse comes before the first write (data copy, seed files, exe)
    seed_objets = seed_dir / "patchset" / "OBJETS.ITD"
    object_count = objets_count(seed_objets) if seed_objets.exists() else 0
    if seed_objets.exists() and is_rehaunted and edition is None:
        return refuse("this seed changes OBJETS.ITD (More Locked Doors), which stock ReHaunted reads "
                      "from its exe, not from disk: install it with --edition")
    indark = find(game, "INDARK.EXE")
    patch_indark = None                   # prepared and verified before anything is written
    if indark:                            # Classic: always the push fix + 400 objects (T4 build)
        h = sha(indark)                   # hints: + the search hint (T7); controls: + the controls
        want = INDARK_CLASSIC_FOR[bool(hints), bool(controls)]
        if h == want:
            pass
        elif h in (GOG_INDARK, INDARK_400, INDARK_CLASSIC) or (h == INDARK_CLASSIC_HINT and hints and controls):
            patch_indark = indark_classic(indark, hints, controls)
            if patch_indark is None:
                return refuse("INDARK.EXE does not take the Classic exe patches (unexpected bytes)")
        elif h in INDARK_CLASSIC_FOR.values():
            return refuse("INDARK.EXE has Classic patches that were not asked for (search hint or "
                          "controls); restore the original INDARK.EXE first")
        elif object_count > 300 and not force:
            return refuse(f"this seed has {object_count} objects and INDARK.EXE (sha256 {h[:16]}) is not "
                          "a known build whose object table can be raised; --force to install anyway")
        else:
            print(f"WARNING: INDARK.EXE (sha256 {h[:16]}) is not a known build: the Classic exe fixes "
                  "(items don't block pushing, 400 objects) are not applied")
    if any(p["file"].upper().startswith("FITD") for p in info["programs"]):
        print("note: FITD is not supported by the randomizer (user decision 2026-10-16); play the "
              "seed with the original game (DOSBox) or the ReHaunted randomizer edition")
    copied = {}
    if data_src is not None:              # before the seed files, so the copied originals get backed up
        for name in VANILLA:
            src = find(data_src, name)
            if src is None or find(game, name):
                continue
            shutil.copy2(src, game / src.name)
            copied[src.name] = sha(game / src.name)
    van = vanilla_hashes()
    plan = []
    for f in files:
        target = find(game, f.name) or game / f.name
        before = sha(target) if target.exists() else None
        if before and before != van.get(f.name.upper()) and not force:
            return refuse(f"{target.name} is not the vanilla file (sha256 {before[:16]}); --force to replace anyway")
        if is_rehaunted and edition is None and f.name.upper() in ("OBJETS.ITD", "DEFINES.ITD"):
            print(f"WARNING: stock ReHaunted reads {f.name} from its embedded data, not from disk; "
                  "this part of the seed needs a ReHaunted build that prefers disk files")
        plan.append((f, target, before))
    backup = game / BACKUP
    backup.mkdir(exist_ok=True)
    manifest = json.loads((seed_dir / "patchset" / "manifest.json").read_text(encoding="utf-8"))
    # generator/options/attempt let reproduce.py regenerate the seed from an F7 capture,
    # which copies this marker into its header
    record = {"seed": manifest.get("seed"), "generator": manifest.get("tool"),
              "options": manifest.get("options"), "attempt": manifest.get("attempt"),
              "seed_dir": seed_dir.name, "installed": time.strftime("%Y-%m-%d %H:%M:%S"),
              "edition": None, "programs": info["programs"], "files": {},
              "copied_data": copied, "data_source": how if data_src else None}   # the kind only (GOG, Steam, CD, chosen folder): no player paths in bug reports
    if controls and (edition is not None or patch_indark is not None or (indark and sha(indark) == INDARK_CLASSIC_FOR[bool(hints), True])):
        # the edition reads it at startup (FitdLib/modernControls.cpp); for the original game the
        # controls are in INDARK.EXE and this only records the choice. Gone with the record on unpatch
        record["modern_controls"] = True
    if keep_aspect and edition is not None:
        # ReHaunted only: the edition reads it at startup (FitdLib/keepAspect.cpp)
        record["keep_aspect"] = True
    for f, target, before in plan:
        if before:
            shutil.copy2(target, backup / target.name)
        shutil.copy2(f, target)
        record["files"][target.name] = {"before": before, "after": sha(target), "backup": bool(before)}
    if edition is not None:
        before = sha(tatou)
        shutil.copy2(tatou, backup / tatou.name)
        shutil.copy2(edition, tatou)
        record["files"][tatou.name] = {"before": before, "after": sha(tatou), "backup": True}
        record["edition"] = EDITION[sha(tatou)]
    if patch_indark:
        before = sha(indark)
        shutil.copy2(indark, backup / indark.name)
        indark.write_bytes(patch_indark)
        record["files"][indark.name] = {"before": before, "after": sha(indark), "backup": True}
        print("  INDARK.EXE: Classic fixes applied (dropped items no longer block pushing furniture; "
              f"object table raised to 400, this seed has {object_count or 'the vanilla'} objects"
              + ("; search hint \"?\" on" if hints else "") +
              "); saves made now do not load in an unpatched INDARK.EXE")
    settings = {}
    if is_rehaunted and info["native_life_scripts"] and fix_config:
        settings["debug.enableNativeLifeScripts"] = "false"
    if edition is not None:               # no automatic data copy over the seed, no self-deploy into GOG/Steam
        settings["gamedata.steamless"] = "true"
    if edition is not None:               # the edition also enforces this itself
        settings["debug.enableNativeLifeScripts"] = "false"
    # every existing config gets the settings; none: both names are created (2.4+ reads
    # aitd_remaster.cfg, 2.3 read aitd_remaster_hd.cfg) and unpatch deletes them again
    cfgs = [find(game, n) for n in CFG_NAMES if find(game, n)] or [game / n for n in CFG_NAMES]
    for cfg in cfgs if settings else []:
        before = sha(cfg) if cfg.exists() else None
        if before:
            shutil.copy2(cfg, backup / cfg.name)
            text = cfg.read_text(encoding="utf-8", errors="replace").splitlines()
        else:
            text = []
        for key, value in settings.items():
            hit = [i for i, l in enumerate(text) if l.strip().startswith(key)]
            for i in hit:
                text[i] = f"{key} = {value}"
            if not hit:
                text.append(f"{key} = {value}")
        cfg.write_text("\n".join(text) + "\n", encoding="utf-8")
        record["files"][cfg.name] = {"before": before, "after": sha(cfg), "backup": before is not None}
    (game / MARKER).write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(f"installed seed {record['seed']} into {game}: {len(record['files'])} file(s), backup in {BACKUP}")
    if record["edition"]:
        print(f"  Tatou.exe replaced by the {record['edition']}")
    if copied:
        print(f"  copied {len(copied)} original game file(s) from {data_src} (removed again by unpatch)")
    for p in info["programs"]:
        print(f"  found {p['file']}: {p['identified_as']}")
    print(SAVE_WARNING)
    return 0


def unpatch(game: Path) -> int:
    game = game.resolve()
    marker = game / MARKER
    if not marker.exists():
        return refuse("no randomizer seed is installed here")
    record = json.loads(marker.read_text(encoding="utf-8"))
    backup = game / BACKUP
    missing = [name for name, f in record["files"].items() if f["backup"] and not (backup / name).is_file()]
    if missing:                          # checked before anything is restored: no half-restored game
        return refuse(f"the backup of {', '.join(missing)} is missing from {BACKUP}; nothing was "
                      "restored. Restore the original game files from your game's store (verify/repair "
                      "the installation), then delete " + MARKER)
    problems = []
    for name, f in record["files"].items():
        target = find(game, name) or game / name
        if target.exists() and sha(target) != f["after"]:
            problems.append(f"{name} changed since install (restoring the backup anyway)")
        if f["backup"]:
            shutil.copy2(backup / name, target)
            if sha(target) != f["before"]:
                return refuse(f"restored {name} does not match its recorded hash; backup kept in {BACKUP}")
        elif target.exists():
            target.unlink()          # the seed added this file
    for name, h in (record.get("copied_data") or {}).items():
        target = game / name
        if target.exists() and sha(target) == h:
            target.unlink()                  # a game file apply copied in
        elif target.exists():
            problems.append(f"{name} (copied in by apply) changed since; left in place")
    shutil.rmtree(backup)
    marker.unlink()
    for p in problems:
        print("note: " + p)
    print(f"unpatched seed {record['seed']}: {len(record['files'])} file(s) restored and verified")
    print(SAVE_WARNING)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detect")
    d.add_argument("game", type=Path)
    p = sub.add_parser("apply")
    p.add_argument("seed_dir", type=Path)
    p.add_argument("game", type=Path)
    p.add_argument("--force", action="store_true")
    p.add_argument("--fix-config", action="store_true")
    p.add_argument("--edition", type=Path, help="AITD Randomizer edition Tatou.exe to install over ReHaunted's")
    p.add_argument("--game-data", type=Path, help="folder with the original game files (else: Steam, GOG, CD search)")
    p.add_argument("--force-data", action="store_true", help="use game files that differ from the GOG release")
    p.add_argument("--hints", action="store_true", help='INDARK.EXE: show an outlined "?" near searchable places')
    p.add_argument("--controls", action="store_true",
                   help="keyboard + mouse controls (ReHaunted edition: flag in the record; INDARK.EXE: --controls patch)")
    p.add_argument("--keep-aspect", action="store_true",
                   help="ReHaunted edition: keep the 16:10 picture with black bars when the window is resized")
    f = sub.add_parser("find-data")
    f.add_argument("folder", type=Path, nargs="?")
    u = sub.add_parser("unpatch")
    u.add_argument("game", type=Path)
    a = ap.parse_args()
    if a.cmd == "detect":
        print(json.dumps(detect(a.game.resolve()), indent=1))
        return 0
    if a.cmd == "apply":
        return apply(a.seed_dir.resolve(), a.game, a.force, a.fix_config, a.edition, a.game_data, a.force_data,
                     a.hints, a.controls, a.keep_aspect)
    if a.cmd == "find-data":
        found = search_game_data()
        for how in ("Steam", "GOG", "CD"):
            hit = dict(found).get(how)
            print(f"{how:6} {'FOUND: ' + str(hit) if hit else 'not found'}")
        cands = ([("folder", a.folder.resolve())] if a.folder else []) + found
        for how, path in cands:
            if not find(path, SENTINEL):
                print(f"{path}: no {SENTINEL}")
                continue
            missing, different = check_game_data(path)
            ok = not missing and not different
            print(f"{path} ({how}): {'matches the GOG release' if ok else 'DIFFERS'}"
                  + (f"; missing {missing}" if missing else "") + (f"; different {different}" if different else ""))
        if not cands:
            print(NO_DATA)
        return 0
    return unpatch(a.game)


if __name__ == "__main__":
    sys.exit(main())
