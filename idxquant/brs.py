"""Berita Resmi Statistik (BRS) BPS — tanggal rilis sesungguhnya.

Ini kunci untuk mencari alpha dari data makro. Korelasi antara nilai ekspor bulan
Mei dan harga saham bulan Mei tidak berguna: angkanya baru diumumkan pertengahan
Juni. Yang bisa diperdagangkan adalah reaksi pasar pada HARI PENGUMUMAN.

Endpoint `pressrelease` memberi `rl_date` — tanggal publikasi resmi tiap rilis,
sehingga event study bisa disandarkan pada saat informasi benar-benar tersedia,
bukan pada periode yang diacu datanya.
"""

from __future__ import annotations

import time

import pandas as pd
import requests

from .bps import BASE, UA, api_key


def ambil_brs(domain: str = "0000", maks_halaman: int = 250,
              jeda: float = 0.15, diam: bool = True) -> pd.DataFrame:
    """Unduh seluruh daftar Berita Resmi Statistik beserta tanggal rilisnya."""
    k = api_key()
    if not k:
        return pd.DataFrame()
    kumpul, hal, total_hal = [], 1, None
    while hal <= maks_halaman:
        u = (f"{BASE}/list/model/pressrelease/lang/ind/domain/{domain}"
             f"/page/{hal}/key/{k}/")
        try:
            r = requests.get(u, headers={"User-Agent": UA}, timeout=30)
            if r.status_code != 200 or not r.text.strip():
                break
            js = r.json()
        except Exception:                                          # noqa: BLE001
            break
        d = js.get("data") if isinstance(js, dict) else None
        if not (isinstance(d, list) and len(d) == 2):
            break
        meta, isi = d[0], d[1]
        if total_hal is None:
            total_hal = int(meta.get("pages", 1))
            if not diam:
                print(f"  {meta.get('total')} rilis dalam {total_hal} halaman")
        kumpul.extend(isi)
        if hal >= total_hal:
            break
        hal += 1
        time.sleep(jeda)

    if not kumpul:
        return pd.DataFrame()
    df = pd.DataFrame(kumpul)
    for c in ("rl_date", "updt_date"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df.sort_values("rl_date").reset_index(drop=True)


# Kata kunci untuk mengelompokkan rilis ke tema yang relevan bagi pasar
TEMA = {
    "Inflasi": r"inflasi|indeks harga konsumen|IHK",
    "Ekspor-Impor": r"ekspor|impor|perdagangan luar negeri|neraca perdagangan",
    "Pertumbuhan Ekonomi": r"pertumbuhan ekonomi|produk domestik bruto|PDB",
    "Ketenagakerjaan": r"ketenagakerjaan|pengangguran|angkatan kerja",
    "Harga Produsen": r"harga produsen|harga perdagangan besar|IHPB",
    "Pariwisata": r"pariwisata|wisatawan mancanegara",
}


def kelompokkan(df: pd.DataFrame) -> pd.DataFrame:
    """Beri label tema pada tiap rilis berdasarkan judulnya."""
    if df.empty or "title" not in df.columns:
        return df
    x = df.copy()
    x["tema"] = None
    for nama, pola in TEMA.items():
        m = x["title"].astype(str).str.contains(pola, case=False, na=False, regex=True)
        x.loc[m & x["tema"].isna(), "tema"] = nama
    return x


def kalender(df: pd.DataFrame, tema: str) -> pd.DatetimeIndex:
    """Tanggal rilis untuk satu tema."""
    x = df[df["tema"] == tema].dropna(subset=["rl_date"])
    return pd.DatetimeIndex(sorted(x["rl_date"].dt.normalize().unique()))
