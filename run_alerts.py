"""Pemantau momentum IDX dengan notifikasi ke HP.

    python run_alerts.py --setup     # tampilkan cara pasang di HP
    python run_alerts.py --tes       # kirim satu notifikasi uji
    python run_alerts.py --sekali    # cek sekali lalu keluar
    python run_alerts.py --pantau    # loop sepanjang jam bursa
    python run_alerts.py --riwayat   # alert yang sudah pernah dikirim
"""

from __future__ import annotations

import argparse
import datetime as dt
import time
import warnings

import pandas as pd

from idxquant import alerts as al
from idxquant import wyckoff as wy
from idxquant.recorder import load_bars, market_open

warnings.filterwarnings("ignore")
WIB = dt.timezone(dt.timedelta(hours=7))
API = "http://127.0.0.1:8848"


def ambil(path, **params):
    import requests
    try:
        r = requests.get(API + path, params=params, timeout=120)
        return r.json() if r.status_code == 200 else {}
    except Exception:                                              # noqa: BLE001
        return {}


def lampirkan_level(rows: list[dict], modal: float | None = None) -> list[dict]:
    """Hitung pivot R1-R3 / S1-S3 dan rencana TP/SL untuk tiap kandidat."""
    from idxquant import data as dl
    from idxquant.levels import analisa_level, format_teks

    for r in rows:
        try:
            d = dl.load(r["ticker"], rng="5y")
            if d is None or len(d) < 30:
                continue
            a = analisa_level(d, modal=modal)
            if a:
                r["level"] = a
                r["level_teks"] = format_teks(r["ticker"], a)
        except Exception:                                          # noqa: BLE001
            continue
    return rows


def kumpulkan_alert(modal: float | None = None) -> list[dict]:
    keluar = []

    # 1. Setup harian yang punya bukti statistik
    scr = ambil("/api/screen", min_turnover=5)
    rows = [r for r in scr.get("rows", []) if r.get("setups")]
    rows = lampirkan_level(rows, modal=modal)
    keluar += al.cek_setup_harian(rows)

    # 2. Momentum intraday
    sc = ambil("/api/scalping", top=20, interval="5m")
    keluar += al.cek_momentum_intraday(sc.get("rows", []))

    # 3. Wyckoff dari bar yang direkam sendiri
    bars = load_bars(interval="5m")
    if not bars.empty:
        wyrows = []
        for t, g in bars.groupby("ticker"):
            s = wy.summarise(t, g.drop(columns=["ticker"]).sort_index())
            if s.get("n_bar", 0) >= 25:
                wyrows.append(s)
        keluar += al.cek_wyckoff(wyrows)

    return keluar


def satu_putaran(kirim_beneran=True, saluran=("ntfy", "telegram", "desktop")):
    a = kumpulkan_alert()
    if not a:
        print(f"  {dt.datetime.now(WIB):%H:%M:%S}  tidak ada alert baru")
        return 0
    terkirim = al.proses(a, kirim_beneran=kirim_beneran, saluran=saluran)
    indiv = [x for x in terkirim if x.get("mode") == "individual"]
    ringkas = [x for x in terkirim if x.get("mode") == "ringkasan"]
    for x in indiv:
        ok = ",".join(k for k, v in (x.get("hasil") or {}).items() if v) or "log-saja"
        print(f"  {dt.datetime.now(WIB):%H:%M:%S}  [P{x['prioritas']}] "
              f"{x['ticker']:6} {x['aturan']:18} -> {ok}")
    if ringkas:
        print(f"  {dt.datetime.now(WIB):%H:%M:%S}  [ringkasan] "
              f"{len(ringkas)} sinyal lain digabung jadi 1 notifikasi")
    print(f"  total notifikasi terkirim: {len(indiv) + (1 if ringkas else 0)} "
          f"(dari {len(terkirim)} sinyal)")
    return len(terkirim)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--tes", action="store_true")
    ap.add_argument("--sekali", action="store_true")
    ap.add_argument("--pantau", action="store_true")
    ap.add_argument("--riwayat", action="store_true")
    ap.add_argument("--telegram", action="store_true", help="pasang notifikasi Telegram")
    ap.add_argument("--token", type=str, default="", help="bot token dari @BotFather")
    ap.add_argument("--level", type=str, default="", help="tampilkan level satu ticker")
    ap.add_argument("--modal", type=float, default=None, help="modal untuk hitung lot")
    ap.add_argument("--interval", type=int, default=180, help="detik antar cek")
    ap.add_argument("--paksa", action="store_true", help="jalan walau bursa tutup")
    a = ap.parse_args()

    topic = al.ntfy_topic()

    if a.level:
        from idxquant import data as dl
        from idxquant.levels import analisa_level, format_teks
        d = dl.load(a.level.upper(), rng="5y")
        if d is None or len(d) < 30:
            print(f"Data {a.level.upper()} tidak cukup.")
            return
        an = analisa_level(d, modal=a.modal)
        print("=" * 52)
        print(f"LEVEL {a.level.upper()}")
        print("=" * 52)
        print(format_teks(a.level.upper(), an))
        if an.get("sizing"):
            s = an["sizing"]
            print(f"\nUkuran posisi (modal Rp{s['modal']:,.0f}, risiko {s['risiko_pct']}%):")
            print(f"  {s['lot']} lot ({s['lembar']:,} lembar) "
                  f"= Rp{s['nilai_posisi']:,.0f} ({s['porsi_modal']}% modal)")
            print(f"  Rugi bila kena SL: Rp{s['rugi_bila_sl']:,.0f}")
        return

    if a.telegram:
        print("=" * 68)
        print("PASANG NOTIFIKASI TELEGRAM")
        print("=" * 68)
        if not a.token:
            print("""
Langkah (dilakukan sendiri di aplikasi Telegram Anda):

  1. Buka Telegram, cari  @BotFather
  2. Kirim  /newbot  lalu ikuti instruksinya (beri nama bot)
  3. BotFather membalas dengan token, bentuknya seperti:
       1234567890:AAF-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  4. Buka bot yang baru Anda buat, tekan START (atau kirim /start)
  5. Jalankan ulang perintah ini dengan token tadi:

       python run_alerts.py --telegram --token "TOKEN_ANDA"

Token disimpan ke data/alert_config.json yang sudah dilindungi .gitignore.
JANGAN menempelkan token langsung ke dalam berkas kode — berkas kode ikut
ter-commit ke GitHub, sedangkan alert_config.json tidak.

Saya tidak bisa membuatkan bot atau mengambil token untuk Anda — itu terikat
akun Telegram pribadi Anda.""")
            return

        cek = al.telegram_cek_token(a.token)
        if not cek.get("ok"):
            print(f"\nToken ditolak: {cek.get('pesan')}")
            print("Pastikan token disalin utuh dari @BotFather.")
            return
        print(f"\nToken valid — bot: {cek['nama']} (@{cek['username']})")

        chats = al.telegram_temukan_chat(a.token)
        if not chats:
            print("\nBelum ada pesan masuk ke bot ini.")
            print(f"Buka Telegram -> cari @{cek['username']} -> tekan START,")
            print("lalu jalankan perintah ini lagi.")
            return

        c = chats[0]
        al.simpan_telegram(a.token, c["chat_id"])
        print(f"Chat ditemukan  : {c['nama']} ({c['tipe']}) id={c['chat_id']}")
        print(f"Tersimpan ke    : {al.CONF_PATH}")
        ok = al.kirim_telegram("IDX Screener — Telegram aktif",
                               "Notifikasi Telegram berhasil dipasang.\n"
                               "Alert akan berisi level R1-R3, support, TP, dan SL.")
        print(f"Uji kirim       : {'berhasil' if ok else 'gagal'}")
        if len(chats) > 1:
            print("\nChat lain terdeteksi (bila salah, set manual "
                  "TELEGRAM_CHAT_ID):")
            for x in chats[1:]:
                print(f"  {x['chat_id']}  {x['nama']} ({x['tipe']})")
        return

    if a.setup:
        print("=" * 68)
        print("PASANG NOTIFIKASI KE HP")
        print("=" * 68)
        print("\n1. Pasang aplikasi ntfy (gratis, tanpa daftar akun):")
        print("     Android : Play Store -> cari 'ntfy'")
        print("     iPhone  : App Store  -> cari 'ntfy'")
        print("\n2. Buka aplikasi, tekan '+', masukkan nama topik ini PERSIS:\n")
        print(f"     {topic}\n")
        print(f"   atau buka di browser HP: https://ntfy.sh/{topic}")
        print("\n3. Uji: python run_alerts.py --tes")
        print("\n4. Jalankan pemantau: python run_alerts.py --pantau")
        print("\n" + "!" * 68)
        print("PENTING: topik ntfy.sh bersifat PUBLIK. Siapa pun yang tahu nama")
        print("topik ini bisa membaca alert Anda. Jangan dibagikan atau di-posting.")
        print("Untuk kerahasiaan penuh, pakai Telegram:")
        print("  setx TELEGRAM_BOT_TOKEN \"token dari @BotFather\"")
        print("  setx TELEGRAM_CHAT_ID   \"chat id Anda\"")
        print("!" * 68)
        return

    if a.tes:
        print(f"Mengirim uji ke topik: {topic}")
        h = al.kirim("IDX Screener — uji notifikasi",
                     "Kalau pesan ini muncul di HP, notifikasi sudah aktif.\n"
                     "Alert sesungguhnya akan berisi ticker, harga, dan alasannya.",
                     prioritas=4, tags="white_check_mark")
        for k, v in h.items():
            print(f"  {k:9} : {'terkirim' if v else 'gagal / belum dikonfigurasi'}")
        return

    if a.riwayat:
        r = al.riwayat(40)
        if not r:
            print("Belum ada alert yang pernah dikirim.")
            return
        df = pd.DataFrame(r)
        print(df.to_string(index=False))
        return

    if a.sekali:
        print(f"Cek sekali · topik {topic}")
        n = satu_putaran()
        print(f"Selesai — {n} alert diproses.")
        return

    if a.pantau:
        print(f"Pemantau aktif · topik {topic} · cek tiap {a.interval} detik")
        print("Ctrl+C untuk berhenti.\n")
        try:
            while True:
                if not market_open() and not a.paksa:
                    print(f"  {dt.datetime.now(WIB):%H:%M:%S}  bursa tutup — menunggu")
                    time.sleep(300)
                    continue
                satu_putaran()
                time.sleep(a.interval)
        except KeyboardInterrupt:
            print("\nPemantau dihentikan.")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
