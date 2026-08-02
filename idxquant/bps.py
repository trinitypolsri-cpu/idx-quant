"""Klien BPS WebAPI — data alternatif Indonesia untuk mencari alpha.

Gagasannya sama seperti yang dipakai dana kuantitatif besar: cari data di luar
harga yang secara ekonomi terhubung dengan emiten tertentu, lalu uji apakah
hubungan itu nyata dan mendahului harga.

Contoh yang relevan untuk IDX:
    arus peti kemas Tanjung Priok  -> emiten logistik/pelayaran (SMDR, TMAS, IPCM)
    volume ekspor batubara         -> ADRO, PTBA, ITMG
    inflasi & penjualan ritel      -> AMRT, MIDI, ACES
    produksi CPO                   -> AALI, LSIP, TAPG

Pasang kunci (didapat dari webapi.bps.go.id, gratis):

    setx BPS_API_KEY "app-id-anda"

Lalu verifikasi:

    python -m idxquant.bps --cek

CATATAN KEJUJURAN: struktur endpoint di bawah disusun dari pola resmi BPS WebAPI v1,
tetapi BELUM pernah saya jalankan dengan kunci sungguhan — probe tanpa kunci hanya
mengembalikan "You are not Allowed to take this action". Karena itu `--cek` menguji
tiap endpoint terhadap API sungguhan dan melaporkan mana yang hidup, alih-alih
menganggap semuanya benar.
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd
import requests

BASE = "https://webapi.bps.go.id/v1/api"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Kode domain BPS
DOMAIN = {
    "nasional": "0000",
    "dki_jakarta": "3100",
    "jakarta_utara": "3175",     # wilayah Pelabuhan Tanjung Priok
}


def api_key() -> str:
    """Ambil kunci dari environment, lalu dari berkas konfigurasi lokal.

    Berkas dipakai sebagai cadangan karena `setx` bisa gagal dengan
    "Access to the registry path is denied" pada mesin yang registry HKCU-nya
    dibatasi kebijakan atau antivirus. data/alert_config.json sudah dilindungi
    .gitignore, jadi kunci tidak ikut ter-commit.
    """
    k = os.getenv("BPS_API_KEY", "")
    if k:
        return k
    try:
        import json

        from .config import DATA_DIR
        p = DATA_DIR / "alert_config.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8")).get("bps_api_key", "")
    except Exception:                                              # noqa: BLE001
        pass
    return ""


def simpan_key(kunci: str) -> str:
    """Simpan kunci BPS ke berkas konfigurasi lokal yang tidak ter-commit."""
    import json

    from .config import DATA_DIR
    p = DATA_DIR / "alert_config.json"
    conf = {}
    if p.exists():
        try:
            conf = json.loads(p.read_text(encoding="utf-8"))
        except Exception:                                          # noqa: BLE001
            conf = {}
    conf["bps_api_key"] = kunci.strip()
    p.write_text(json.dumps(conf, indent=2), encoding="utf-8")
    return str(p)


def _get(path: str, **params) -> dict | None:
    k = api_key()
    if not k:
        return None
    try:
        r = requests.get(f"{BASE}/{path.strip('/')}/key/{k}/",
                         headers={"User-Agent": UA}, params=params, timeout=30)
        if r.status_code != 200:
            return None
        js = r.json()
        if isinstance(js, dict) and str(js.get("status", "")).lower() == "error":
            return {"_error": js.get("message", "ditolak")}
        return js
    except Exception as e:                                         # noqa: BLE001
        return {"_error": str(e)}


# ------------------------------------------------------------------ penjelajahan
def daftar_subjek(domain: str = "0000") -> pd.DataFrame:
    js = _get(f"list/model/subject/domain/{domain}")
    return _ke_frame(js)


def semua_variabel(domain: str = "0000", maks_halaman: int = 80,
                   diam: bool = True) -> pd.DataFrame:
    """Telusuri SELURUH halaman daftar variabel.

    BPS mengembalikan 10 variabel per halaman dan menaruh metadata paginasi di
    data[0] ({'page','pages','per_page','count','total'}). Tanpa menelusuri
    halaman, pencarian hanya melihat 10 dari ratusan indikator yang tersedia.
    """
    kumpul, halaman = [], 1
    total_hal = None
    while halaman <= maks_halaman:
        js = _get(f"list/model/var/domain/{domain}", page=str(halaman))
        if not js or "_error" in js:
            break
        d = js.get("data")
        if not (isinstance(d, list) and len(d) == 2):
            break
        meta, isi = d[0], d[1]
        if total_hal is None:
            total_hal = int(meta.get("pages", 1))
            if not diam:
                print(f"  {meta.get('total')} variabel dalam {total_hal} halaman")
        kumpul.extend(isi)
        if halaman >= total_hal:
            break
        halaman += 1
    return pd.DataFrame(kumpul)


def cari_variabel(kata: str, domain: str = "0000") -> pd.DataFrame:
    """Cari indikator berdasarkan kata kunci, mis. 'peti kemas', 'ekspor'.

    Menerima beberapa kata kunci dipisah '|' (contoh: 'peti kemas|kontainer').
    """
    df = semua_variabel(domain=domain)
    if df.empty or "title" not in df.columns:
        return df
    pola = "|".join(k.strip() for k in kata.split("|") if k.strip())
    return df[df["title"].astype(str).str.contains(pola, case=False, na=False,
                                                   regex=True)]


BULAN = {1: "Januari", 2: "Februari", 3: "Maret", 4: "April", 5: "Mei", 6: "Juni",
         7: "Juli", 8: "Agustus", 9: "September", 10: "Oktober", 11: "November",
         12: "Desember", 13: "Tahunan"}


def th_id(tahun: int) -> int:
    """BPS memakai ID tahun = tahun kalender - 1900 (2023 -> 123)."""
    return tahun - 1900


def ambil_data(var_id: str | int, tahun: int, domain: str = "0000") -> pd.DataFrame:
    """Ambil satu variabel untuk satu tahun, dikembalikan sebagai deret bulanan.

    Endpoint yang BEKERJA adalah bentuk path penuh dengan `lang` dan `th` sebagai
    ID tahun BPS. Bentuk query-string (?var=..&th=2023) mengembalikan metadata
    tanpa datacontent, sehingga tampak "berhasil" padahal kosong — jebakan yang
    mudah membuat orang menyimpulkan datanya tidak ada.
    """
    k = api_key()
    if not k:
        return pd.DataFrame()
    t = th_id(tahun)
    url = (f"{BASE}/list/model/data/lang/ind/domain/{domain}"
           f"/var/{var_id}/th/{t}/key/{k}/")
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200 or not r.text.strip():
            return pd.DataFrame()
        js = r.json()
    except Exception:                                              # noqa: BLE001
        return pd.DataFrame()
    if not isinstance(js, dict):
        return pd.DataFrame()

    dc = js.get("datacontent") or {}
    if not dc:
        return pd.DataFrame()
    satuan = ((js.get("var") or [{}])[0]).get("unit", "")
    label = ((js.get("var") or [{}])[0]).get("label", str(var_id))

    ts = str(t)
    rows = []
    for kunci, nilai in dc.items():
        # Kunci: <wilayah><var><turvar><th><turth>. Panjang var/turvar bervariasi,
        # jadi diurai dari BELAKANG memakai th yang sudah diketahui.
        bulan = None
        for n_turth in (1, 2):
            if len(kunci) > n_turth + 3 and kunci[-(n_turth + 3):-n_turth] == ts:
                bulan = kunci[-n_turth:]
                break
        if bulan is None:
            continue
        try:
            b = int(bulan)
        except ValueError:
            continue
        # Banyak variabel terpecah per wilayah (152 kota untuk inflasi). Tanpa
        # menyimpan kode wilayah, seluruh kota tertumpuk pada bulan yang sama dan
        # menghasilkan deret yang tampak panjang tapi tidak bermakna.
        wilayah = kunci[: -(len(kunci) - kunci.find(str(var_id)))] if str(var_id) in kunci else ""
        rows.append({"tahun": tahun, "bulan": b, "periode": BULAN.get(b, b),
                     "wilayah": wilayah, "nilai": float(nilai)})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df.attrs["satuan"] = satuan
    df.attrs["label"] = label
    return df.sort_values("bulan").reset_index(drop=True)


def deret_bulanan(var_id: str | int, dari: int, sampai: int,
                  domain: str = "0000", jeda: float = 0.2,
                  wilayah: str = "9999") -> pd.Series:
    """Gabungkan beberapa tahun menjadi satu deret bulanan berindeks tanggal.

    `wilayah` menyaring dimensi daerah; 9999 = INDONESIA (agregat nasional).
    Variabel yang tidak berdimensi wilayah tidak terpengaruh.
    """
    import time as _t
    potong = []
    satuan = label = ""
    for th in range(dari, sampai + 1):
        d = ambil_data(var_id, th, domain=domain)
        if not d.empty:
            satuan = satuan or d.attrs.get("satuan", "")
            label = label or d.attrs.get("label", "")
            potong.append(d[d["bulan"].between(1, 12)])
        _t.sleep(jeda)
    if not potong:
        return pd.Series(dtype=float)
    df = pd.concat(potong)

    if wilayah and "wilayah" in df.columns:
        kode = set(df["wilayah"].astype(str))
        if wilayah in kode:
            df = df[df["wilayah"].astype(str) == wilayah]
        elif len(kode) > 3:
            # Ada dimensi wilayah tapi kode nasional tidak ditemukan: menjumlah
            # atau mengambil sembarang kota akan menyesatkan, jadi hentikan.
            raise ValueError(
                f"var {var_id} terpecah ke {len(kode)} wilayah dan kode "
                f"'{wilayah}' tidak ada. Pilih kode wilayah yang benar "
                f"secara eksplisit; menggabungkan seluruh wilayah menghasilkan "
                f"deret yang tidak bermakna.")

    df = df.drop_duplicates(subset=["tahun", "bulan"], keep="last")
    idx = pd.to_datetime(dict(year=df["tahun"], month=df["bulan"], day=1))
    s = pd.Series(df["nilai"].to_numpy(), index=idx, name=label or str(var_id))
    s = s.sort_index()
    s.attrs["satuan"] = satuan
    return s


def _ke_frame(js) -> pd.DataFrame:
    if not js or "_error" in js:
        return pd.DataFrame()
    d = js.get("data") if isinstance(js, dict) else js
    # BPS sering membungkus: data = [meta, [isi]]
    if isinstance(d, list) and len(d) == 2 and isinstance(d[1], list):
        d = d[1]
    return pd.DataFrame(d) if isinstance(d, list) else pd.DataFrame()


def _bongkar_datacontent(js: dict) -> pd.DataFrame:
    """BPS mengemas nilai di 'datacontent' dengan kunci gabungan var+turvar+th+turth."""
    isi = js.get("datacontent") or {}
    if not isi:
        return pd.DataFrame()
    tahun = {str(x.get("val")): x.get("label") for x in (js.get("tahun") or [])}
    turth = {str(x.get("val")): x.get("label") for x in (js.get("turtahun") or [])}
    rows = []
    for kunci, nilai in isi.items():
        rows.append({"kunci": kunci, "nilai": nilai})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Kunci: <var><turvar><thn><turthn> — panjang bagian bervariasi, jadi
    # pencocokan dilakukan lewat sufiks tahun/turtahun yang dikenal.
    def urai(k: str):
        for th_val, th_lab in tahun.items():
            for tt_val, tt_lab in turth.items():
                if k.endswith(th_val + tt_val.zfill(len(tt_val))):
                    return th_lab, tt_lab
        return None, None
    df[["tahun", "periode"]] = df["kunci"].apply(lambda k: pd.Series(urai(k)))
    return df


# ------------------------------------------------------------------ verifikasi
def cek() -> None:
    k = api_key()
    print("=" * 70)
    print("CEK KONEKSI BPS WEBAPI")
    print("=" * 70)
    if not k:
        print("\nBPS_API_KEY belum diset.")
        print('  setx BPS_API_KEY "app-id-anda"')
        print("\nDaftar gratis di https://webapi.bps.go.id")
        sys.exit(1)
    print(f"\nKunci terpasang: {k[:6]}...{k[-4:]} ({len(k)} karakter)\n")

    uji = [
        ("daftar subjek nasional", f"list/model/subject/domain/0000", {}),
        ("daftar variabel nasional", f"list/model/var/domain/0000", {}),
        ("daftar subjek Jakarta Utara", f"list/model/subject/domain/3175", {}),
        ("daftar variabel Jakarta Utara", f"list/model/var/domain/3175", {}),
    ]
    hidup = 0
    for nama, path, p in uji:
        js = _get(path, **p)
        if js is None:
            print(f"  [gagal ] {nama} — tidak ada respons")
        elif "_error" in js:
            print(f"  [tolak ] {nama} — {js['_error']}")
        else:
            df = _ke_frame(js)
            print(f"  [OK    ] {nama} — {len(df)} baris")
            if len(df):
                print(f"            kolom: {list(df.columns)[:6]}")
            hidup += 1
    print(f"\n{hidup}/{len(uji)} endpoint merespons.")
    if hidup:
        print("Lanjutkan dengan:  python -m idxquant.bps --cari 'peti kemas'")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Klien BPS WebAPI")
    ap.add_argument("--pasang", type=str, help="simpan API key ke konfigurasi lokal")
    ap.add_argument("--cek", action="store_true", help="uji koneksi & endpoint")
    ap.add_argument("--cari", type=str, help="cari variabel berdasarkan kata kunci")
    ap.add_argument("--domain", type=str, default="0000", help="kode domain BPS")
    ap.add_argument("--data", type=str, help="ambil deret waktu satu var_id")
    a = ap.parse_args()

    if a.pasang:
        lokasi = simpan_key(a.pasang)
        print(f"Kunci BPS tersimpan ({len(a.pasang.strip())} karakter) di:\n  {lokasi}")
        print("\nBerkas ini dilindungi .gitignore — tidak akan ter-commit.")
        print("Lanjutkan: python -m idxquant.bps --cek")
    elif a.cek:
        cek()
    elif a.cari:
        df = cari_variabel(a.cari, domain=a.domain)
        print(df.head(30).to_string() if len(df) else "tidak ada hasil / kunci ditolak")
    elif a.data:
        df = ambil_data(a.data, domain=a.domain)
        print(df.head(40).to_string() if len(df) else "tidak ada data")
    else:
        ap.print_help()
