"""A synthetic Rig Manager library on disk: every source kind kemperrig reads, and one of
each thing `analyze` and `doctor` report. The smoke test runs every command against it;
`bin/run sample DIR` writes one to look at by hand.

Run as a script: `python tests/_sample.py DIR [--force]`.
"""

from __future__ import annotations

import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _fixture import build_rmbackup, build_snapshot  # noqa: E402
from _pack_fixture import build_pack, krig, pack_rig  # noqa: E402
from _payloads import (  # noqa: E402
    _track_body,
    amp_msg,
    f08_msg,
    make_blob,
    module_msg,
    performance_blob,
    rig_track,
    string_msg,
)

DEVICE = "KPA-SAMPLE"
CRITERIA = Path(__file__).resolve().parents[1] / "config" / "example-shortlist.json"
_CAB = "Cab V30"
_IR = "Cab 4x12 V30.wav"


@dataclass(frozen=True)
class SamplePaths:
    root: Path
    backup: Path
    live: Path
    snapshots: list[Path]
    rigpack: Path
    presetpack: Path
    criteria: Path


def _track(name: str, gain: float, *, cab: str | None = None, ir: str | None = None,
           effects: tuple = (), f08_pages: tuple = (), f08_amp: bool = False) -> list[bytes]:
    track = rig_track(name, cab=cab)
    if ir:
        track.append(string_msg(ir, 0x05))
    track.append(amp_msg(gain, func=0x08, length=74) if f08_amp else amp_msg(gain))
    track += [module_msg(page, params) for page, params in effects]
    track += [f08_msg(page) for page in f08_pages]
    return track


_RHYTHM = _track("Recto Rhythm", 7.0, cab=_CAB, ir=_IR,
                 effects=((0x32, [33, 0, 0, 1]), (0x3c, [164, 0, 0, 1]), (0x3d, [178, 0, 0, 1])))
_LEAD = _track("Recto Lead", 8.2, cab=_CAB, effects=((0x32, [33, 0, 0, 1]),
                                                       (0x3d, [177, 0, 0, 0])))
_PLEXI = _track("Plexi Crunch", 5.5)
_LEGACY = _track("Legacy Room", 3.0, f08_pages=(0x4b,), f08_amp=True)
_CLEAN_BODY = _track_body(_track("Clean Sparkle", 2.0, effects=((0x3a, [97, 0, 0, 1]),)))


def _rig(name: str, folder: str, gain: str, amp: str, blob: bytes, **kw) -> dict:
    return {"name": name, "folder": folder, "gain": gain, "amp_model": amp, "blob": blob,
            "author": kw.get("author", "Profile Co"),
            "cabinet_name": kw.get("cabinet_name", "N/A"),
            "amp_comment": kw.get("amp_comment", "N/A")}


def _rigs() -> list[dict]:
    plexi = make_blob([_PLEXI])
    return [
        _rig("Recto Rhythm", "Amps/Recto", "7.0", "Dual Rectifier", make_blob([_RHYTHM]),
             amp_comment="TS808 boost"),
        _rig("Recto Lead", "Amps/Recto", "8.2", "Dual Rectifier", make_blob([_LEAD]),
             amp_comment="TS808 boost"),
        _rig("Broken Rig", "Amps/Recto", "6.0", "Dual Rectifier",
             make_blob([_track("Broken Rig", 6.0)])[:-4]),
        _rig("Plexi Crunch", "Amps/Plexi", "5.5", "Plexi 1959", plexi,
             author="Second Author", cabinet_name="4x12 Greenback", amp_comment="no boost"),
        _rig("Plexi Crunch", "Imported", "5.5", "Plexi 1959", plexi,
             author="Second Author", cabinet_name="4x12 Greenback", amp_comment="no boost"),
        _rig("Spare Lead", "Amps/Plexi", "6.5", "JCM800",
             make_blob([_track("Spare Lead", 6.5)])),
        _rig("Clean Sparkle", "Amps/Clean", "2.0", "Twin Reverb", krig(_CLEAN_BODY)),
        _rig("Legacy Room", "Amps/Clean", "3.0", "AC30", make_blob([_LEGACY]),
             cabinet_name="2x12 Alnico"),
    ]


RIG_NAMES = sorted({r["name"] for r in _rigs()})


def _performance(name: str, *slots: tuple[str, str, list[bytes]]) -> dict:
    return {"name": name,
            "slots": [{"name": label, "rig_name": rig, "amp_name": "-"}
                      for label, rig, _ in slots],
            "blob": performance_blob(*(track for _, _, track in slots))}


def _performances() -> list[dict]:
    gone = _track("Gone Rig", 4.0)
    return [
        _performance("Recto Set", ("Rhythm", "Recto Rhythm", _RHYTHM),
                     ("Lead", "Recto Lead", _LEAD)),
        _performance("Plexi Set", ("Crunch", "Plexi Crunch", _PLEXI),
                     ("Clean", "Clean Sparkle", _track("Clean Sparkle", 2.0))),
        _performance("Mixed Set", ("Room", "Legacy Room", _LEGACY),
                     ("Rhythm", "Recto Rhythm", _RHYTHM), ("Gone", "Gone Rig", gone)),
    ]


def _presets() -> list[dict]:
    def cab(name: str) -> dict:
        return {"name": name, "preset_class": "6",
                "blob": make_blob([[string_msg(name, 0x20)]])}
    return [cab(_CAB), cab("Cab Greenback"),
            {"name": "Delay Long", "preset_class": "2", "preset_type": "Delay",
             "blob": make_blob([[module_msg(0x3c, [164, 0, 0, 1])]])}]


def _unfoldered(rigs: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in rigs:
        if r["name"] not in seen:
            seen.add(r["name"])
            out.append({k: v for k, v in r.items() if k != "folder"})
    return out


def _write_live(backup: Path, live: Path) -> None:
    with zipfile.ZipFile(backup) as zf:
        for entry in zf.namelist():
            if entry != "info.xml":
                zf.extract(entry, live)


def _write_packs(live: Path) -> tuple[Path, Path]:
    (live / "Rig Packs").mkdir(parents=True, exist_ok=True)
    (live / "Preset Packs").mkdir(parents=True, exist_ok=True)
    rigpack = Path(build_pack(str(live / "Rig Packs" / "Sample.rigpack"), name="Sample Pack",
                              author="Sample Vendor", rigs=[
                                  pack_rig("Clean Sparkle", body=_CLEAN_BODY),
                                  pack_rig("Recto Rhythm", gain=6.0),
                                  pack_rig("Pack Lead", gain=7.5)]))
    spring = _track_body([module_msg(0x3d, [181, 0, 0, 1])])
    presetpack = Path(build_pack(str(live / "Preset Packs" / "Sample.presetpack"),
                                 name="Sample Presets", author="Sample Vendor",
                                 content="Presets", rigs=[pack_rig("Spring Hall", body=spring)]))
    return rigpack, presetpack


def build_sample(dest: str | Path) -> SamplePaths:
    """Write the sample library into `dest`, creating it; files of the same names are replaced."""
    root = Path(dest)
    root.mkdir(parents=True, exist_ok=True)
    rigs, performances, presets = _rigs(), _performances(), _presets()
    backup = Path(build_rmbackup(str(root / "Library.rmbackup"), rigs=rigs,
                                 performances=performances, presets=presets,
                                 user="Sample Player"))
    live = root / "RigManager"
    _write_live(backup, live)
    snaps = live / "Backups"
    snaps.mkdir(exist_ok=True)
    older = _unfoldered([r for r in rigs if r["name"] != "Spare Lead"])
    newer = _unfoldered(rigs)
    newer[1] = {**newer[1], "gain": "8.4",
                "blob": make_blob([_track("Recto Lead", 8.4, cab=_CAB)])}
    snapshots = [Path(build_snapshot(str(snaps / f"{DEVICE} - {stamp}R2.db"), rigs=rs,
                                     performances=performances, presets=presets))
                 for stamp, rs in (("2026-01-01 10-00-00", older),
                                   ("2026-02-01 10-00-00", newer))]
    rigpack, presetpack = _write_packs(live)
    criteria = root / "criteria.json"
    criteria.write_text(CRITERIA.read_text())
    return SamplePaths(root, backup, live, snapshots, rigpack, presetpack, criteria)


def _refusal(dest: Path, force: bool) -> str | None:
    from kemperrig.model import library_root
    if library_root(dest) is not None:
        return f"{dest}: inside a Rig Manager library — choose another folder"
    if dest.exists() and not dest.is_dir():
        return f"{dest}: exists and is not a folder"
    if dest.is_dir() and any(dest.iterdir()) and not force:
        return f"{dest}: not empty — pass --force to write the sample into it anyway"
    return None


def main(argv: list[str]) -> int:
    args = [a for a in argv if a != "--force"]
    if len(args) != 1:
        print("usage: bin/run sample DIR [--force]", file=sys.stderr)
        return 2
    dest = Path(args[0])
    why = _refusal(dest, "--force" in argv)
    if why:
        print(f"sample: {why}", file=sys.stderr)
        return 2
    paths = build_sample(dest)
    print(f"wrote a sample library to {paths.root}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
