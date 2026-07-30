// Validasi: jalankan skrip inline dashboard dengan DOM tiruan, cek output SVG.
const fs = require("fs");
const html = fs.readFileSync("dashboard.html", "utf8");

const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.error("FAIL: blok <script> tidak ditemukan"); process.exit(1); }

const sink = {};
const document = {
  getElementById(id) {
    return { set innerHTML(v) { sink[id] = v; }, get innerHTML() { return sink[id]; } };
  },
};

try {
  new Function("document", m[1])(document);
} catch (e) {
  console.error("FAIL: skrip melempar error ->", e.message);
  process.exit(1);
}

let bad = 0;
for (const [id, want] of [["eq", "path"], ["br", "path"], ["sect", "<tr>"]]) {
  const out = sink[id];
  if (!out || out.length < 200) { console.error(`FAIL: #${id} kosong/terlalu pendek`); bad++; continue; }
  if (!out.includes(want)) { console.error(`FAIL: #${id} tidak memuat "${want}"`); bad++; continue; }
  if (/NaN|undefined|Infinity/.test(out)) {
    console.error(`FAIL: #${id} memuat NaN/undefined/Infinity`);
    console.error("      " + out.match(/.{0,60}(NaN|undefined|Infinity).{0,60}/)[0]);
    bad++; continue;
  }
  console.log(`OK   #${id}: ${out.length} char, ${(out.match(/<(path|rect|tr|line|circle)/g) || []).length} elemen`);
}

// Cek konsistensi: baris tabel sektor harus 11
const rows = (sink.sect.match(/<tr>/g) || []).length;
console.log(`OK   tabel sektor: ${rows} baris`);
if (rows !== 11) { console.error("FAIL: jumlah baris sektor tidak 11"); bad++; }

// Cek struktur HTML dasar
const opens = (html.match(/<(div|section|table|tbody|thead|tr|td|th|ul|li|span|p|svg)\b/g) || []).length;
const closes = (html.match(/<\/(div|section|table|tbody|thead|tr|td|th|ul|li|span|p|svg)>/g) || []).length;
console.log(`INFO tag blok: ${opens} buka / ${closes} tutup`);
if (opens !== closes) { console.error(`FAIL: tag tidak seimbang (selisih ${opens - closes})`); bad++; }

// Token tema harus terdefinisi di ketiga blok
for (const sel of [":root{", "prefers-color-scheme: dark", 'data-theme="dark"', 'data-theme="light"']) {
  if (!html.includes(sel)) { console.error(`FAIL: blok tema hilang -> ${sel}`); bad++; }
}
console.log(bad === 0 ? "\nSEMUA CEK LULUS" : `\n${bad} CEK GAGAL`);
process.exit(bad ? 1 : 0);
