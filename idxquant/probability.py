"""Lapisan probabilistik: model terkalibrasi, bukan skor buatan tangan.

Skor heuristik (bobot 30/20/18 yang ditetapkan manusia) punya dua kelemahan:
bobotnya tebakan, dan keluarannya bukan probabilitas — angka 70 tidak berarti
"70% kemungkinan". Modul ini menggantinya dengan regresi logistik yang dicocokkan
ke data, sehingga keluarannya adalah peluang sesungguhnya dan bisa diuji kalibrasinya.

Yang diukur:
  AUC          kemampuan memeringkat (0,5 = seperti melempar koin)
  Brier score  ketepatan probabilitas (makin kecil makin baik)
  Kalibrasi    kalau model bilang 10%, apakah benar terjadi ~10% waktu?
  Lift         berapa kali lebih baik dari base rate

Semua diuji SECARA TEMPORAL: dilatih pada masa lalu, diuji pada masa depan.
Membagi data secara acak akan membocorkan informasi masa depan dan membuat model
tampak jauh lebih baik daripada kenyataannya.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler


def auc(y, p) -> float:
    try:
        return float(roc_auc_score(y, p))
    except Exception:                                              # noqa: BLE001
        return float("nan")


def brier(y, p) -> float:
    try:
        return float(brier_score_loss(y, p))
    except Exception:                                              # noqa: BLE001
        return float("nan")


def tabel_kalibrasi(y: np.ndarray, p: np.ndarray, n_bin: int = 8) -> pd.DataFrame:
    """Apakah probabilitas yang diramalkan cocok dengan kenyataan?"""
    df = pd.DataFrame({"y": np.asarray(y, float), "p": np.asarray(p, float)})
    # Bin berdasarkan kuantil agar tiap kelompok berisi cukup observasi
    try:
        df["bin"] = pd.qcut(df["p"], n_bin, duplicates="drop")
    except ValueError:
        df["bin"] = pd.cut(df["p"], n_bin)
    g = df.groupby("bin", observed=True).agg(
        N=("y", "size"), diramal=("p", "mean"), terjadi=("y", "mean"))
    g["diramal%"] = (g["diramal"] * 100).round(3)
    g["terjadi%"] = (g["terjadi"] * 100).round(3)
    g["selisih"] = (g["terjadi%"] - g["diramal%"]).round(3)
    return g[["N", "diramal%", "terjadi%", "selisih"]]


class ModelProbabilitas:
    """Regresi logistik dengan penskalaan dan penanganan kelas timpang.

    ARA terjadi 0,17% waktu — sangat timpang. `class_weight='balanced'` mencegah
    model menyerah dan meramalkan 'tidak pernah' untuk semuanya.
    """

    def __init__(self, fitur: list[str], C: float = 1.0):
        self.fitur = fitur
        self.scaler = StandardScaler()
        self.model = LogisticRegression(
            C=C, max_iter=2000, class_weight="balanced", solver="lbfgs")
        self.terlatih = False

    def _X(self, df: pd.DataFrame) -> np.ndarray:
        X = df[self.fitur].astype(float)
        return X.replace([np.inf, -np.inf], np.nan).fillna(X.median()).to_numpy()

    def latih(self, df: pd.DataFrame, target: str):
        X = self.scaler.fit_transform(self._X(df))
        self.model.fit(X, df[target].astype(int).to_numpy())
        self.terlatih = True
        return self

    def peluang(self, df: pd.DataFrame) -> np.ndarray:
        if not self.terlatih:
            raise RuntimeError("model belum dilatih")
        return self.model.predict_proba(self.scaler.transform(self._X(df)))[:, 1]

    def koefisien(self) -> pd.DataFrame:
        """Arah dan kekuatan tiap fitur, dalam satuan odds ratio."""
        c = self.model.coef_[0]
        return (pd.DataFrame({"fitur": self.fitur, "koef": c,
                              "odds_ratio": np.exp(c)})
                .sort_values("koef", key=abs, ascending=False)
                .reset_index(drop=True))


def uji_temporal(df: pd.DataFrame, fitur: list[str], target: str,
                 frac_latih: float = 0.5, frac_kalib: float = 0.2) -> dict:
    """Latih -> kalibrasi -> uji, dibagi menurut WAKTU dalam tiga bagian.

    Bagian kalibrasi wajib ada. `class_weight='balanced'` menghasilkan peringkat
    yang baik tetapi probabilitas yang sangat berlebihan: pada kejadian langka
    (0,17%) model bisa mengeluarkan angka 81% untuk peristiwa yang sebenarnya
    terjadi 1% waktu. Regresi isotonik pada potongan terpisah mengembalikan angka
    itu ke skala yang benar, tanpa merusak kemampuan memeringkat.
    """
    from sklearn.isotonic import IsotonicRegression

    d = df.sort_index()
    n = int(len(d) * frac_latih)
    nk = n + int(len(d) * frac_kalib)
    tr, ka, te = d.iloc[:n], d.iloc[n:nk], d.iloc[nk:]
    if tr[target].sum() < 20 or te[target].sum() < 10 or ka[target].sum() < 5:
        return {"error": "kejadian positif terlalu sedikit"}

    m = ModelProbabilitas(fitur).latih(tr, target)

    # Kalibrasi pada potongan yang belum pernah dilihat model
    p_ka = m.peluang(ka)
    y_ka = ka[target].astype(int).to_numpy()
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(p_ka, y_ka)

    p_te_mentah = m.peluang(te)
    p_te = iso.predict(p_te_mentah)
    y_te = te[target].astype(int).to_numpy()
    base = float(y_te.mean())

    # Lift pada desil teratas
    k = max(1, len(p_te) // 10)
    idx = np.argsort(-p_te)[:k]
    lift10 = float(y_te[idx].mean() / base) if base > 0 else np.nan

    return {
        "model": m, "kalibrator": iso,
        "n_latih": len(tr), "n_kalib": len(ka), "n_uji": len(te),
        "base_uji": base,
        "auc": auc(y_te, p_te),
        "auc_mentah": auc(y_te, p_te_mentah),
        "brier": brier(y_te, p_te),
        "brier_mentah": brier(y_te, p_te_mentah),
        "lift_desil1": lift10,
        "p_desil1": float(y_te[idx].mean()),
        "kalibrasi": tabel_kalibrasi(y_te, p_te),
        "kalibrasi_mentah": tabel_kalibrasi(y_te, p_te_mentah),
        "koefisien": m.koefisien(),
        "y_uji": y_te, "p_uji": p_te, "p_uji_mentah": p_te_mentah,
        # Posisi potong, BUKAN label indeks: indeks berisi tanggal yang berulang
        # antar emiten, sehingga .loc dengan daftar tanggal memicu ekspansi
        # kartesian raksasa. Potongan UJI dimulai setelah bagian kalibrasi,
        # jadi pemanggil harus memakai df.sort_index().iloc[split_uji:].
        "split_latih": n, "split_uji": nk,
    }


def bandingkan(y: np.ndarray, kandidat: dict[str, np.ndarray]) -> pd.DataFrame:
    """Bandingkan beberapa penilai pada data uji yang sama."""
    base = float(np.mean(y))
    rows = []
    for nama, p in kandidat.items():
        p = np.asarray(p, float)
        k = max(1, len(p) // 10)
        idx = np.argsort(-p)[:k]
        rows.append({
            "Penilai": nama,
            "AUC": round(auc(y, p), 4),
            "Desil-1 P%": round(float(y[idx].mean()) * 100, 3),
            "Lift desil-1": round(float(y[idx].mean() / base), 1) if base else np.nan,
        })
    return pd.DataFrame(rows).sort_values("AUC", ascending=False)


def bootstrap_ci(y: np.ndarray, p: np.ndarray, n_sim: int = 500,
                 seed: int = 11) -> tuple[float, float]:
    """Selang kepercayaan 95% untuk AUC lewat bootstrap."""
    rng = np.random.default_rng(seed)
    n = len(y)
    vals = []
    for _ in range(n_sim):
        i = rng.integers(0, n, n)
        if len(np.unique(y[i])) < 2:
            continue
        vals.append(auc(y[i], p[i]))
    if not vals:
        return (np.nan, np.nan)
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))
