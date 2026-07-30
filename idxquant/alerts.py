"""Notifikasi momentum — ke HP (ntfy/Telegram), desktop, dan log.

KEAMANAN: topik ntfy.sh bersifat PUBLIK. Siapa pun yang tahu nama topiknya bisa
membaca alert Anda. Karena itu nama topik dibuat acak panjang dan disimpan lokal.
Jangan dibagikan. Untuk kerahasiaan sungguhan, pakai Telegram.

Konfigurasi (opsional — tanpa ini alert tetap tercatat di log dan desktop):

    setx NTFY_TOPIC          "topik-acak-anda"
    setx TELEGRAM_BOT_TOKEN  "token-dari-@BotFather"
    setx TELEGRAM_CHAT_ID    "chat-id-anda"
"""

from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import sqlite3
import subprocess

import requests

from .config import DATA_DIR

WIB = dt.timezone(dt.timedelta(hours=7))
ALERT_DB = DATA_DIR / "alerts.db"
CONF_PATH = DATA_DIR / "alert_config.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS terkirim (
    kunci   TEXT PRIMARY KEY,
    ticker  TEXT, aturan TEXT, waktu TEXT, pesan TEXT, prioritas INTEGER
);
CREATE INDEX IF NOT EXISTS idx_alert_waktu ON terkirim(waktu);
"""


def _con():
    con = sqlite3.connect(ALERT_DB, timeout=20)
    con.executescript(SCHEMA)
    return con


# ------------------------------------------------------------------ konfigurasi
def load_config() -> dict:
    conf = {}
    if CONF_PATH.exists():
        try:
            conf = json.loads(CONF_PATH.read_text(encoding="utf-8"))
        except Exception:                                          # noqa: BLE001
            conf = {}
    if not conf.get("ntfy_topic"):
        # Topik acak 20 karakter — cukup panjang agar tidak bisa ditebak.
        conf["ntfy_topic"] = "idxq-" + secrets.token_urlsafe(15).replace("-", "").replace("_", "")[:20]
        CONF_PATH.write_text(json.dumps(conf, indent=2), encoding="utf-8")
    return conf


def ntfy_topic() -> str:
    return os.getenv("NTFY_TOPIC") or load_config()["ntfy_topic"]


# ------------------------------------------------------------------ saluran
def kirim_ntfy(judul: str, pesan: str, prioritas: int = 3,
               tags: str = "chart_with_upwards_trend", klik: str = "") -> bool:
    topic = ntfy_topic()
    if not topic:
        return False
    h = {"Title": judul.encode("utf-8"), "Priority": str(prioritas),
         "Tags": tags}
    if klik:
        h["Click"] = klik
    try:
        r = requests.post(f"https://ntfy.sh/{topic}", data=pesan.encode("utf-8"),
                          headers=h, timeout=15)
        return r.status_code == 200
    except Exception:                                              # noqa: BLE001
        return False


def _tg_conf() -> tuple[str, str]:
    conf = load_config()
    tok = os.getenv("TELEGRAM_BOT_TOKEN") or conf.get("telegram_token", "")
    chat = os.getenv("TELEGRAM_CHAT_ID") or conf.get("telegram_chat_id", "")
    return tok, chat


def kirim_telegram(judul: str, pesan: str) -> bool:
    tok, chat = _tg_conf()
    if not tok or not chat:
        return False
    try:
        # MarkdownV2 rewel soal escaping; pakai HTML yang lebih toleran.
        esc = lambda s: (s.replace("&", "&amp;").replace("<", "&lt;")   # noqa: E731
                          .replace(">", "&gt;"))
        teks = f"<b>{esc(judul)}</b>\n<pre>{esc(pesan)}</pre>"
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          json={"chat_id": chat, "text": teks,
                                "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=15)
        return r.status_code == 200
    except Exception:                                              # noqa: BLE001
        return False


def telegram_cek_token(token: str) -> dict:
    """Validasi token bot ke Telegram."""
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=15)
        js = r.json()
        if js.get("ok"):
            u = js["result"]
            return {"ok": True, "nama": u.get("first_name"),
                    "username": u.get("username")}
        return {"ok": False, "pesan": js.get("description", "token ditolak")}
    except Exception as e:                                         # noqa: BLE001
        return {"ok": False, "pesan": str(e)}


def telegram_temukan_chat(token: str) -> list[dict]:
    """Ambil chat_id dari pesan yang sudah dikirim pengguna ke bot.

    Alurnya: pengguna kirim /start ke bot-nya, lalu fungsi ini membaca getUpdates
    untuk menemukan chat_id — supaya tidak perlu mencarinya manual.
    """
    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
        js = r.json()
        if not js.get("ok"):
            return []
        keluar, lihat = [], set()
        for u in js.get("result", []):
            msg = u.get("message") or u.get("channel_post") or {}
            chat = msg.get("chat") or {}
            cid = chat.get("id")
            if cid and cid not in lihat:
                lihat.add(cid)
                keluar.append({
                    "chat_id": str(cid), "tipe": chat.get("type"),
                    "nama": chat.get("first_name") or chat.get("title") or "",
                    "username": chat.get("username", ""),
                })
        return keluar
    except Exception:                                              # noqa: BLE001
        return []


def simpan_telegram(token: str, chat_id: str) -> None:
    conf = load_config()
    conf["telegram_token"] = token
    conf["telegram_chat_id"] = chat_id
    CONF_PATH.write_text(json.dumps(conf, indent=2), encoding="utf-8")


def kirim_desktop(judul: str, pesan: str) -> bool:
    """Notifikasi toast Windows lewat PowerShell — tanpa dependensi tambahan."""
    if os.name != "nt":
        return False
    ps = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null
$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
     [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$n = $t.GetElementsByTagName("text")
$n.Item(0).AppendChild($t.CreateTextNode({json.dumps(judul)})) > $null
$n.Item(1).AppendChild($t.CreateTextNode({json.dumps(pesan)})) > $null
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("IDX Screener").Show(
     [Windows.UI.Notifications.ToastNotification]::new($t))
"""
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, timeout=20)
        return True
    except Exception:                                              # noqa: BLE001
        return False


def kirim(judul: str, pesan: str, prioritas: int = 3, tags: str = "chart_with_upwards_trend",
          saluran: tuple[str, ...] = ("ntfy", "telegram", "desktop")) -> dict:
    hasil = {}
    if "ntfy" in saluran:
        hasil["ntfy"] = kirim_ntfy(judul, pesan, prioritas, tags)
    if "telegram" in saluran:
        hasil["telegram"] = kirim_telegram(judul, pesan)
    if "desktop" in saluran:
        hasil["desktop"] = kirim_desktop(judul, pesan)
    return hasil


# ------------------------------------------------------------------ dedup
def sudah_dikirim(kunci: str, cooldown_menit: int = 120) -> bool:
    con = _con()
    try:
        row = con.execute("SELECT waktu FROM terkirim WHERE kunci=?", (kunci,)).fetchone()
        if not row:
            return False
        t = dt.datetime.fromisoformat(row[0])
        return (dt.datetime.now(WIB) - t).total_seconds() < cooldown_menit * 60
    finally:
        con.close()


def catat(kunci: str, ticker: str, aturan: str, pesan: str, prioritas: int):
    con = _con()
    try:
        con.execute("INSERT OR REPLACE INTO terkirim VALUES (?,?,?,?,?,?)",
                    (kunci, ticker, aturan,
                     dt.datetime.now(WIB).isoformat(timespec="seconds"),
                     pesan, prioritas))
        con.commit()
    finally:
        con.close()


def riwayat(limit: int = 50) -> list[dict]:
    con = _con()
    try:
        rows = con.execute(
            "SELECT ticker, aturan, waktu, pesan, prioritas FROM terkirim "
            "ORDER BY waktu DESC LIMIT ?", (limit,)).fetchall()
        return [{"ticker": r[0], "aturan": r[1], "waktu": r[2],
                 "pesan": r[3], "prioritas": r[4]} for r in rows]
    finally:
        con.close()


# ------------------------------------------------------------------ aturan
# Hanya setup dengan bukti statistik yang memicu prioritas tinggi. RSLeader dan
# PullbackUptrend sengaja TIDAK memicu alert: t-stat 0,89 dan 0,44 — tidak
# signifikan, jadi memberi notifikasi untuk keduanya hanya melatih Anda
# mengabaikan notifikasi.
ATURAN_SETUP = {
    "BaseBreakout":    {"prioritas": 5, "tag": "rotating_light", "edge": 1.58},
    "SqueezeBreakout": {"prioritas": 4, "tag": "chart_with_upwards_trend", "edge": 1.01},
    "TrendTemplate":   {"prioritas": 3, "tag": "chart_with_upwards_trend", "edge": 0.58},
}


def cek_setup_harian(scan_rows: list[dict], cooldown_menit: int = 720) -> list[dict]:
    """Alert bila emiten memicu setup harian yang punya bukti."""
    keluar = []
    hari = dt.datetime.now(WIB).strftime("%Y-%m-%d")
    for r in scan_rows:
        for s in r.get("setups", []):
            cfg = ATURAN_SETUP.get(s)
            if not cfg:
                continue
            kunci = f"{hari}|{r['ticker']}|{s}"
            if sudah_dikirim(kunci, cooldown_menit):
                continue
            judul = f"{r['ticker']} — {s}"
            pesan = (f"Harga {r['close']:,.0f} · skor {r['skor']:.0f}\n"
                     f"1 bln {r.get('ret_1m',0):+.1f}% · 3 bln {r.get('ret_3m',0):+.1f}%\n"
                     f"Edge historis +{cfg['edge']:.2f}% per 21 hari")
            if r.get("level_teks"):
                pesan += "\n\n" + r["level_teks"]
            keluar.append({"kunci": kunci, "ticker": r["ticker"], "aturan": s,
                           "judul": judul, "pesan": pesan,
                           "prioritas": cfg["prioritas"], "tag": cfg["tag"]})
    return keluar


def cek_momentum_intraday(scalp_rows: list[dict], min_skor: float = 85,
                          min_rvol: float = 1.5, cooldown_menit: int = 90) -> list[dict]:
    """Alert momentum kenaikan intraday: skor tinggi, di atas VWAP, volume menguat."""
    keluar = []
    jam = dt.datetime.now(WIB).strftime("%Y-%m-%d %H")
    for r in scalp_rows:
        if (r.get("skor") or 0) < min_skor:
            continue
        if (r.get("vs_vwap") or -1) <= 0:
            continue
        if (r.get("rvol") or 0) < min_rvol:
            continue
        # Jangan beri sinyal masuk kalau ruang ke ARA sudah habis
        if r.get("ara_head") is not None and r["ara_head"] < 3:
            continue
        # Jangan beri sinyal kalau gesekan memakan sebagian besar gerak
        if (r.get("peluang") or 0) < 2:
            continue

        kunci = f"{jam}|{r['ticker']}|momentum"
        if sudah_dikirim(kunci, cooldown_menit):
            continue
        judul = f"{r['ticker']} momentum naik"
        pesan = (f"Harga {r['harga']:,.0f} · sesi {r['ret_sesi']:+.2f}%\n"
                 f"vs VWAP {r['vs_vwap']:+.2f}% · RVol {r['rvol']:.2f}x\n"
                 f"Biaya putar {r['biaya_putaran']:.2f}% · peluang {r['peluang']:.1f}x")
        if r.get("ara_head") is not None:
            pesan += f"\nSisa ARA {r['ara_head']:.1f}%"
        keluar.append({"kunci": kunci, "ticker": r["ticker"], "aturan": "MomentumIntraday",
                       "judul": judul, "pesan": pesan, "prioritas": 4,
                       "tag": "rocket"})
    return keluar


def cek_wyckoff(wy_rows: list[dict], cooldown_menit: int = 120) -> list[dict]:
    """Alert bila Wyckoff menunjukkan Sign of Strength atau Spring."""
    keluar = []
    jam = dt.datetime.now(WIB).strftime("%Y-%m-%d %H")
    for r in wy_rows:
        ev = r.get("event_terakhir")
        if ev not in ("SOS", "SPR"):
            continue
        if (r.get("vs_vwap") or -1) <= 0:
            continue
        # SOS terlalu sering muncul untuk dijadikan alert apa adanya — pada satu sesi
        # uji, 13 dari 25 emiten memicunya. Syarat tambahan agar tetap jadi sinyal
        # langka: bias akumulasi, minimal 3 peristiwa bullish, dan harga benar-benar
        # diterima di atas VWAP.
        if r.get("bias") != "akumulasi":
            continue
        if (r.get("bullish") or 0) < 3:
            continue
        if (r.get("penerimaan_atas_vwap") or 0) < 80:
            continue
        if (r.get("bearish") or 0) > 1:
            continue
        kunci = f"{jam}|{r['ticker']}|wy{ev}"
        if sudah_dikirim(kunci, cooldown_menit):
            continue
        nama = "Sign of Strength" if ev == "SOS" else "Spring"
        judul = f"{r['ticker']} Wyckoff {nama}"
        pesan = (f"Harga {r['harga']:,.0f} · VWAP {r['vwap']:,.0f} "
                 f"({r['vs_vwap']:+.2f}%)\n"
                 f"Bias {r['bias']} · {r['bullish']} bullish / {r['bearish']} bearish\n"
                 f"Penerimaan di atas VWAP {r.get('penerimaan_atas_vwap',0):.0f}%")
        keluar.append({"kunci": kunci, "ticker": r["ticker"], "aturan": f"Wyckoff{ev}",
                       "judul": judul, "pesan": pesan, "prioritas": 4, "tag": "bell"})
    return keluar


def proses(alerts: list[dict], kirim_beneran: bool = True,
           saluran: tuple[str, ...] = ("ntfy", "telegram", "desktop"),
           maks_individual: int = 5) -> list[dict]:
    """Kirim alert dengan batas jumlah, catat, kembalikan yang diproses.

    Notifikasi yang terlalu banyak sama buruknya dengan tidak ada notifikasi —
    penerimanya berhenti membaca. Maka hanya `maks_individual` alert berprioritas
    tertinggi yang dikirim satu per satu; sisanya digabung menjadi SATU ringkasan.
    """
    urut = sorted(alerts, key=lambda x: (-x["prioritas"], x["ticker"]))
    utama, sisa = urut[:maks_individual], urut[maks_individual:]
    diproses = []

    for a in utama:
        hasil = {}
        if kirim_beneran:
            hasil = kirim(a["judul"], a["pesan"], a["prioritas"], a["tag"], saluran)
        catat(a["kunci"], a["ticker"], a["aturan"], a["pesan"], a["prioritas"])
        a["hasil"] = hasil
        a["mode"] = "individual"
        diproses.append(a)

    if sisa:
        per_aturan: dict[str, list[str]] = {}
        for a in sisa:
            per_aturan.setdefault(a["aturan"], []).append(a["ticker"])
        baris = [f"{k}: {', '.join(sorted(set(v)))}" for k, v in sorted(per_aturan.items())]
        pesan = "\n".join(baris)
        judul = f"+{len(sisa)} sinyal lain"
        hasil = kirim(judul, pesan, 2, "clipboard", saluran) if kirim_beneran else {}
        for a in sisa:
            catat(a["kunci"], a["ticker"], a["aturan"], a["pesan"], a["prioritas"])
            a["hasil"] = hasil
            a["mode"] = "ringkasan"
            diproses.append(a)

    return diproses
