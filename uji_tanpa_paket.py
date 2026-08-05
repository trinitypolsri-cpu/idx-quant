"""Uji ketahanan build_static bila paket opsional tidak terpasang.

Mensimulasikan lingkungan CI yang menyebabkan kegagalan 3-4 Agustus 2026:
scipy dan scikit-learn tidak ada. Data inti (screener, sektor, scalping, level)
HARUS tetap terbit; hanya model gabungan yang boleh dilewati.

    python uji_tanpa_paket.py
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import runpy
import sys

DIBLOKIR = {"sklearn", "scipy"}


class Pemblokir(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in DIBLOKIR:
            raise ImportError(f"No module named '{fullname}' (disimulasikan)")
        return None


if __name__ == "__main__":
    sys.meta_path.insert(0, Pemblokir())
    print("=" * 70)
    print(f"UJI: build_static.py --alert tanpa {', '.join(sorted(DIBLOKIR))}")
    print("=" * 70)
    # WAJIB sama persis dengan perintah di .github/workflows/idx-monitor.yml.
    # Bug KeyError 'close' lolos ke produksi karena uji ini memakai perintah TANPA
    # --alert, sedangkan CI memakainya — jalur alert tidak pernah tersentuh.
    sys.argv = ["build_static.py", "--alert"]
    try:
        runpy.run_path("build_static.py", run_name="__main__")
    except SystemExit:
        pass
    except Exception as e:                                          # noqa: BLE001
        print(f"\n>>> BUILD MASIH GAGAL: {type(e).__name__}: {e}")
        raise SystemExit(1)

    import json
    import pathlib
    wajib = ["ringkasan", "screener", "sektor", "level", "chart"]
    print()
    kurang = []
    for f in wajib:
        p = pathlib.Path("docs/data") / f"{f}.json"
        if p.exists() and p.stat().st_size > 50:
            print(f"  OK    {f}.json  ({p.stat().st_size/1024:.0f} KB)")
        else:
            print(f"  HILANG {f}.json")
            kurang.append(f)
    print()
    if kurang:
        print(f">>> GAGAL: {kurang} tidak terbit")
        raise SystemExit(1)
    print(">>> LULUS: data inti tetap terbit tanpa paket opsional")
