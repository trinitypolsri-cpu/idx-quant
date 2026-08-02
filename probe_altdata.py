"""Probe data alternatif Indonesia — apakah benar bisa diambil program?"""

from __future__ import annotations

import time

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
H = {"User-Agent": UA, "Accept": "application/json, text/html, */*"}

TARGET = [
    ("BPS WebAPI - daftar domain",
     "https://webapi.bps.go.id/v1/api/domain/type/all/key/DEMO/", {}),
    ("BPS WebAPI - daftar subjek",
     "https://webapi.bps.go.id/v1/api/list/model/subject/domain/0000/key/DEMO/", {}),
    ("BPS situs utama (HTML)",
     "https://www.bps.go.id/id", {}),
    ("BPS tabel bongkar muat pelabuhan",
     "https://www.bps.go.id/en/statistics-table/2/NjgjMg==/bongkar-muat-barang-angkutan-laut-antar-pulau-di-pelabuhan-utama.html", {}),
    ("BPS Jakarta Utara - kontainer ekspor",
     "https://jakutkota.bps.go.id/en/statistics-table/2/NjA1IzI=/volume-ekspor-kontainer-melalui-pelabuhan-tanjung-priok-menurut-bulan.html", {}),
    ("Bank Indonesia - statistik",
     "https://www.bi.go.id/id/statistik/ekonomi-keuangan/seki/Default.aspx", {}),
    ("Kemendag - harga bahan pokok",
     "https://ews.kemendag.go.id/api/v1/price", {}),
]


def probe(nama, url, params):
    t0 = time.time()
    try:
        r = requests.get(url, headers=H, params=params, timeout=25)
        ms = (time.time() - t0) * 1000
        ct = r.headers.get("content-type", "")[:32]
        out = f"[{r.status_code}] {nama}\n     {ms:.0f}ms · {ct} · {len(r.content):,} byte"
        body = r.text[:220].replace("\n", " ").replace("\r", "")
        out += f"\n     {body}"
        return out
    except Exception as e:                                        # noqa: BLE001
        return f"[ERR] {nama}\n     {type(e).__name__}: {str(e)[:140]}"


if __name__ == "__main__":
    print("=" * 80)
    print("PROBE DATA ALTERNATIF INDONESIA")
    print("=" * 80)
    for t in TARGET:
        print()
        print(probe(*t))
