"""Helper deploy — sambungkan repo lokal ke GitHub tanpa salah ketik username.

    python setup_github.py USERNAME_GITHUB_ANDA

Melakukan pemeriksaan keamanan dulu (token tidak boleh ikut ter-commit), lalu
menyetel remote dan push. Tidak menyentuh apa pun bila pemeriksaan gagal.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAMA_REPO = "idx-quant"


def jalankan(*args, cek=True):
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if cek and r.returncode != 0:
        print(f"  gagal: {' '.join(args)}")
        print("  " + (r.stderr or r.stdout).strip()[:400])
        sys.exit(1)
    return (r.stdout or "").strip()


def periksa_keamanan() -> bool:
    """Pastikan tidak ada rahasia yang akan terunggah."""
    print("\n[1/5] Pemeriksaan keamanan")
    aman = True

    terlacak = jalankan("git", "ls-files").split()
    bocor = [f for f in terlacak if "alert_config" in f or f.endswith((".db", ".env"))]
    if bocor:
        print(f"  BAHAYA berkas rahasia ter-track: {bocor}")
        aman = False
    else:
        print("  OK  tidak ada alert_config.json / *.db yang ter-track")

    # Cari token Telegram sungguhan di seluruh berkas ter-track
    pola = re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{33,}")
    conf = ROOT / "data" / "alert_config.json"
    token_asli = ""
    if conf.exists():
        try:
            token_asli = json.loads(conf.read_text(encoding="utf-8")).get("telegram_token", "")
        except Exception:                                          # noqa: BLE001
            pass

    kena = []
    for f in terlacak:
        p = ROOT / f
        if not p.is_file():
            continue
        try:
            t = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:                                          # noqa: BLE001
            continue
        if token_asli and token_asli in t:
            kena.append(f)
        elif pola.search(t) and "1234567890" not in t:
            kena.append(f)
    if kena:
        print(f"  BAHAYA token Telegram ditemukan di: {kena}")
        aman = False
    else:
        print("  OK  tidak ada token Telegram di berkas ter-track")

    # Periksa riwayat git
    riwayat = jalankan("git", "log", "--all", "-p", cek=False)
    if token_asli and token_asli in riwayat:
        print("  BAHAYA token Telegram ada di RIWAYAT git")
        aman = False
    else:
        print("  OK  riwayat git bersih")

    return aman


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("Contoh:  python setup_github.py budisantoso")
        sys.exit(1)

    user = sys.argv[1].strip().strip("/")
    if user.upper() == "USERNAME" or not re.fullmatch(r"[A-Za-z0-9-]{1,39}", user):
        print(f"Username '{user}' tidak valid.")
        print("Isi dengan username GitHub Anda yang sebenarnya, bukan kata 'USERNAME'.")
        sys.exit(1)

    url = f"https://github.com/{user}/{NAMA_REPO}.git"
    print("=" * 66)
    print("DEPLOY KE GITHUB")
    print("=" * 66)
    print(f"  username : {user}")
    print(f"  repo     : {url}")

    if not periksa_keamanan():
        print("\nDIHENTIKAN. Perbaiki temuan di atas sebelum push.")
        sys.exit(1)

    print("\n[2/5] Commit perubahan yang tersisa")
    kotor = jalankan("git", "status", "--porcelain")
    if kotor:
        jalankan("git", "add", "-A")
        jalankan("git", "commit", "-m", "tambah analisis BSJP, seasonal, dan overnight")
        print(f"  {len(kotor.splitlines())} berkas di-commit")
    else:
        print("  tidak ada perubahan")

    print("\n[3/5] Cek repo di GitHub")
    ada = subprocess.run(["git", "ls-remote", url], cwd=ROOT,
                         capture_output=True, text=True).returncode == 0
    if not ada:
        print(f"  Repo belum ada atau belum bisa diakses.")
        print(f"\n  Buat dulu di: https://github.com/new")
        print(f"    Repository name : {NAMA_REPO}")
        print(f"    Visibility      : Public  (wajib agar GitHub Pages gratis)")
        print(f"    JANGAN centang 'Add a README file'")
        print(f"\n  Lalu jalankan lagi: python setup_github.py {user}")
        sys.exit(1)
    print("  OK  repo ditemukan")

    print("\n[4/5] Setel remote dan push")
    jalankan("git", "remote", "remove", "origin", cek=False)
    jalankan("git", "remote", "add", "origin", url)
    jalankan("git", "branch", "-M", "main")
    print("  mendorong ke GitHub (browser mungkin meminta login)...")
    jalankan("git", "push", "-u", "origin", "main")
    print("  OK  ter-push")

    print("\n[5/5] Langkah terakhir — dilakukan di browser")
    base = f"https://github.com/{user}/{NAMA_REPO}"
    print(f"""
  A. Simpan token sebagai Secret
     {base}/settings/secrets/actions
     Tambah 2 secret:
       TELEGRAM_BOT_TOKEN  dan  TELEGRAM_CHAT_ID
     Nilainya lihat dengan:  python setup_github.py --token

  B. Nyalakan GitHub Pages
     {base}/settings/pages
       Source : Deploy from a branch
       Branch : main   Folder : /docs   -> Save

  C. Jalankan workflow pertama kali
     {base}/actions
       klik 'IDX Monitor' -> 'Run workflow'

  D. Buka dari HP (tunggu ~3 menit setelah workflow selesai)
     https://{user}.github.io/{NAMA_REPO}/
     Lalu 'Add to Home Screen'
""")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--token":
        c = ROOT / "data" / "alert_config.json"
        if not c.exists():
            print("data/alert_config.json belum ada. Jalankan dulu:")
            print('  python run_alerts.py --telegram --token "TOKEN_ANDA"')
            sys.exit(1)
        d = json.loads(c.read_text(encoding="utf-8"))
        print("Salin nilai ini ke GitHub Secrets:\n")
        print(f"  TELEGRAM_BOT_TOKEN = {d.get('telegram_token') or '(belum dipasang)'}")
        print(f"  TELEGRAM_CHAT_ID   = {d.get('telegram_chat_id') or '(belum dipasang)'}")
        print(f"  NTFY_TOPIC         = {d.get('ntfy_topic') or '-'}")
        print("\nJangan tempelkan nilai ini ke dalam berkas kode.")
        sys.exit(0)
    main()
