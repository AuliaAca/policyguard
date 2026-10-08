"""Konsol moderasi PolicyGuard (Streamlit). Hanya memanggil API; tidak mengakses database langsung.

Menjalankan (lokal):  python scripts/run_local.py      (API + dashboard sekaligus)
Menjalankan (Docker): docker compose up --build        (dashboard di http://localhost:8501)

Alamat API dan API key dicari berurutan dari:
  1. environment variable POLICYGUARD_API_URL / POLICYGUARD_API_KEY
  2. environment variable DASHBOARD_API_KEY (Docker membacanya dari .env)
  3. file .env di folder project: DASHBOARD_API_KEY, atau key pertama di SERVICE_API_KEYS
Keduanya bisa diubah di sidebar (tombol > di kiri atas).

Konsep tampilan: teks listing disajikan seperti berkas yang sedang diperiksa reviewer.
Bagian yang ditandai sistem diberi stabilo, dengan catatan pasal di sebelahnya.
"""
import html
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

import altair as alt
import httpx
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------- konfigurasi koneksi

def read_env_file(path: Path) -> dict[str, str]:
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    return values


def default_settings() -> tuple[str, str]:
    env_file = read_env_file(Path(__file__).resolve().parents[1] / ".env")
    url = os.environ.get("POLICYGUARD_API_URL", "http://localhost:8000")
    first_service_key = env_file.get("SERVICE_API_KEYS", "").split(",")[0].strip()
    key = (os.environ.get("POLICYGUARD_API_KEY") or os.environ.get("DASHBOARD_API_KEY")
           or env_file.get("DASHBOARD_API_KEY") or first_service_key)
    return url, key


# ---------------------------------------------------------------- teks dan label

REASONS = {   # review_reason -> (label singkat untuk daftar, penjelasan untuk berkas)
    "rule_soft_hit": ("Kata berisiko", "Ada kata yang cocok dengan rules soft. Mode tanpa AI tidak bisa menilai konteksnya."),
    "rule_llm_disagree": ("AI dan rules berbeda", "AI menilai listing patuh, tetapi ada kata berisiko yang cocok dengan rules."),
    "low_confidence": ("AI ragu", "AI tidak cukup yakin untuk memutuskan secara otomatis."),
    "insufficient_info": ("Informasi kurang", "Ada sinyal pelanggaran, tetapi teks listing tidak cukup untuk memastikan."),
    "llm_unavailable": ("AI tidak tersedia", "AI tidak bisa dihubungi saat listing diperiksa."),
    "invalid_llm_output": ("Jawaban AI tidak valid", "Jawaban AI dua kali gagal validasi (pasal atau kutipan tidak cocok)."),
    "retrieval_unavailable": ("Pasal tidak terambil", "Pasal kebijakan tidak bisa diambil saat listing diperiksa."),
}
DECISIONS = {"approve": "Disetujui", "reject": "Ditolak", "needs_review": "Perlu review"}
DECIDED_BY = {"rule": "Rules", "llm": "AI", "fallback": "Fallback (komponen gagal)"}
# Warna status dari palet tervalidasi; selalu dipasangkan dengan label teks, tidak pernah warna saja.
STATUS = {"approve": ("#0CA30C", "#0A6B0A"), "reject": ("#D03B3B", "#A12828"), "needs_review": ("#FAB219", "#7A5200")}
SERIES = "#2A78D6"   # satu seri data: satu warna


def rupiah(n: int) -> str:
    return "Rp" + f"{n:,}".replace(",", ".")


def ago(iso: str) -> str:
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    s = int((datetime.now(timezone.utc) - t).total_seconds())
    if s < 60:
        return "baru saja"
    if s < 3600:
        return f"{s // 60} menit lalu"
    if s < 86400:
        return f"{s // 3600} jam lalu"
    return f"{s // 86400} hari lalu"


def short_policy(pid: str) -> str:
    return pid.removeprefix("POL-")


# ---------------------------------------------------------------- stabilo pada teks listing
# Rules mencocokkan teks yang sudah dinormalisasi (alpr4 -> alpra). Supaya stabilo jatuh di
# kata aslinya, normalisasi yang sama diterapkan per kata di sini.

_LEET = str.maketrans({"4": "a", "1": "i", "0": "o", "3": "e", "5": "s", "7": "t"})
_UNIT = re.compile(r"^\d+(?:[.,]\d+)?[a-z]{0,3}$")


def _norm_word(w: str) -> str:
    w = re.sub(r"[.\-_*]", "", w.lower()) if re.fullmatch(r"(?:[a-zA-Z][.\-_*])+[a-zA-Z]", w) else w.lower()
    if any(c.isalpha() for c in w) and any(c.isdigit() for c in w) and not _UNIT.match(w):
        w = w.translate(_LEET)
    return w


def find_spans(text: str, rule_hits: list[dict], violations: list[dict]) -> list[tuple[int, int, str, set]]:
    """Mengembalikan [(awal, akhir, jenis, {policy_id})]. jenis: 'strong' (bukti pelanggaran) atau 'soft'."""
    words = [(m.start(), m.end(), _norm_word(m.group().strip(".,;:!?()\"'"))) for m in re.finditer(r"\S+", text)]
    spans = []
    for h in rule_hits:
        term = h["term"].split()
        for i in range(len(words) - len(term) + 1):
            if [w[2] for w in words[i:i + len(term)]] == term:
                kind = "strong" if h["kind"] == "hard" else "soft"
                spans.append((words[i][0], words[i + len(term) - 1][1], kind, {h["policy_id"]}))
    for v in violations:
        pattern = r"\s+".join(map(re.escape, v["evidence"].split()))
        for m in re.finditer(pattern, text, flags=re.IGNORECASE) if pattern else []:
            spans.append((m.start(), m.end(), "strong", {v["policy_id"]}))
    spans.sort()
    merged = []
    for s, e, kind, pids in spans:
        if merged and s <= merged[-1][1]:
            ps, pe, pk, ppids = merged[-1]
            merged[-1] = (ps, max(pe, e), "strong" if "strong" in (pk, kind) else "soft", ppids | pids)
        else:
            merged.append((s, e, kind, set(pids)))
    return merged


def highlighted(text: str, spans) -> str:
    out, pos = [], 0
    for s, e, kind, pids in spans:
        # Cocokan rules sedikit melebar (tanda baca): rapikan supaya stabilo hanya di kata.
        out.append(html.escape(text[pos:s]))
        tags = " ".join(short_policy(p) for p in sorted(pids))
        out.append(f'<mark class="hl-{kind}">{html.escape(text[s:e])}</mark><sup class="note-{kind}">{tags}</sup>')
        pos = e
    out.append(html.escape(text[pos:]))
    return "".join(out)


# ---------------------------------------------------------------- gaya

CSS = """
<style>
:root {
  --ink: #18222D; --ink-2: #596572; --rule: #D2D9DF; --canvas: #EEF1F3; --paper: #FFFFFF;
  --pen: #2B44B8; --hl: #FFE36E; --hl-soft: #FFF3BF;
}
.block-container { padding-top: 3.25rem; padding-bottom: 3rem; max-width: 1360px; }
h1, h2, h3 { letter-spacing: -0.01em; }

.pg-head { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: .5rem 2rem;
           padding-bottom: .9rem; border-bottom: 1px solid var(--rule); margin-bottom: 1rem; }
.pg-brand { font-size: 1.35rem; font-weight: 700; color: var(--ink); }
.pg-brand span { font-weight: 400; color: var(--ink-2); margin-left: .6rem; font-size: 1rem; }
.pg-env { display: flex; gap: 1.25rem; flex-wrap: wrap; color: var(--ink-2); font-size: .85rem; }
.pg-env b { color: var(--ink); font-weight: 600; }
.dot { display: inline-block; width: .55rem; height: .55rem; border-radius: 50%; margin-right: .35rem; vertical-align: .05rem; }

.pg-kpis { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); background: var(--paper);
           border: 1px solid var(--rule); border-radius: 4px; margin-bottom: 1.25rem; }
.pg-kpi { padding: .8rem 1rem; border-left: 1px solid var(--rule); }
.pg-kpi:first-child { border-left: none; }
.pg-kpi .v { font-size: 1.6rem; font-weight: 600; font-variant-numeric: tabular-nums; line-height: 1.2; color: var(--ink); }
.pg-kpi .l { font-size: .82rem; color: var(--ink-2); }
@media (max-width: 760px) {
  .pg-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .pg-kpi { border-left: none; border-top: 1px solid var(--rule); }
}

/* Daftar antrian: radio button ditampilkan sebagai daftar berkas (selector untuk Streamlit 1.5x/1.6x) */
.st-key-queue { background: var(--paper); border: 1px solid var(--rule); border-radius: 4px; }
.st-key-queue [role="radiogroup"] { gap: 0; width: 100%; align-items: stretch; }
.st-key-queue [role="radiogroup"] > div { width: 100%; box-sizing: border-box; padding: .65rem .85rem .7rem; border-bottom: 1px solid var(--rule);
           border-left: 3px solid transparent; }
.st-key-queue [role="radiogroup"] > div:last-child { border-bottom: none; }
.st-key-queue [role="radiogroup"] > div[data-selected="true"] { border-left-color: var(--pen); background: #F3F5FC; }
.st-key-queue [data-testid="stRadioOption"] { width: 100%; cursor: pointer; }
.st-key-queue [data-testid="stRadioOption"] > div > div:not([data-testid]) { display: none; }
.st-key-queue [data-testid="stRadioOption"] p { font-weight: 600; line-height: 1.35; }
.st-key-queue [data-testid="stRadioCaption"] { padding-left: 0; margin-left: 0; }
.st-key-queue [data-testid="stRadioOption"][data-focus-visible="true"] { outline: 2px solid var(--pen); outline-offset: 2px; }

/* Berkas listing */
.case { background: var(--paper); border: 1px solid var(--rule); border-radius: 4px; padding: 1.25rem 1.5rem; }
.case-top { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; }
.case-id { color: var(--ink-2); font-size: .85rem; }
.verdict { font-size: .85rem; font-weight: 600; white-space: nowrap; }
.meta { display: flex; flex-wrap: wrap; gap: .4rem 2rem; margin: .6rem 0 1rem; font-size: .9rem; color: var(--ink-2); }
.meta b { color: var(--ink); font-weight: 600; }
.why { padding: .6rem .8rem; background: #FFF8E6; border-left: 3px solid #FAB219; font-size: .92rem; margin-bottom: 1rem; }
.doc { font-family: "Atkinson Hyperlegible", "Public Sans", sans-serif; color: var(--ink);
       border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule); padding: 1rem 0; }
.doc .t { font-size: 1.35rem; font-weight: 700; line-height: 1.45; margin: 0 0 .4rem; }
.doc .d { font-size: 1.05rem; line-height: 1.7; margin: 0; white-space: pre-wrap; max-width: 72ch; }
.doc .empty { color: var(--ink-2); font-style: italic; font-size: .95rem; }
mark.hl-strong { background: var(--hl); color: inherit; padding: 0 .12em; border-radius: 2px; box-decoration-break: clone; }
mark.hl-soft { background: linear-gradient(transparent 55%, var(--hl-soft) 55%); color: inherit; padding: 0 .08em; }
sup.note-strong, sup.note-soft { font-family: "Public Sans", sans-serif; font-size: .62em; font-weight: 700;
       margin-left: .15em; letter-spacing: .01em; }
sup.note-strong { color: var(--pen); }
sup.note-soft { color: var(--ink-2); font-weight: 600; }
.legend { font-size: .8rem; color: var(--ink-2); margin-top: .5rem; display: flex; gap: 1.5rem; flex-wrap: wrap; }
.legend mark { font-size: .8rem; }
.signals { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem 1.5rem; margin-top: 1rem; font-size: .88rem; }
.signals h4 { font-size: .82rem; font-weight: 600; color: var(--ink-2); margin: 0 0 .35rem; padding: 0; }
.chip { display: inline-block; border: 1px solid var(--rule); border-radius: 3px; padding: .05rem .4rem; margin: 0 .3rem .3rem 0; font-size: .82rem; }
.chip.pen { border-color: #C3CBEE; color: var(--pen); }
.muted { color: var(--ink-2); }
.meter { height: 6px; background: #E3E8EC; border-radius: 3px; margin: .35rem 0 .2rem; max-width: 12rem; }
.meter i { display: block; height: 100%; background: var(--pen); border-radius: 3px; }
.sug { margin: .45rem 0 0; line-height: 1.4; }
.sug b { color: var(--pen); }
.llm-err { color: #A12828; font-size: .85rem; margin-top: .75rem; }
@media (max-width: 760px) { .signals { grid-template-columns: 1fr; } }

/* Pasal terpilih di kotak pilihan: tinta pulpen, bukan blok warna penuh */
[data-testid="stMultiSelect"] [data-tag] { background: #E8ECFA; color: var(--pen); }
[data-testid="stMultiSelect"] [data-tag] * { color: var(--pen); }

/* Tombol keputusan */
.st-key-btn_approve button { background: #0A6B0A; border-color: #0A6B0A; color: #fff; }
.st-key-btn_reject button { background: #A12828; border-color: #A12828; color: #fff; }
.st-key-btn_approve button:hover, .st-key-btn_reject button:hover { filter: brightness(1.12); color: #fff; }

.empty-state { background: var(--paper); border: 1px dashed var(--rule); border-radius: 4px; padding: 2.5rem 1.5rem; text-align: center; }
.empty-state p { margin: .3rem 0; color: var(--ink-2); }
.empty-state p:first-child { color: var(--ink); font-weight: 600; font-size: 1.05rem; }
.empty-state code { font-size: .85rem; }
</style>
"""

# ---------------------------------------------------------------- API

st.set_page_config(page_title="PolicyGuard: konsol moderasi", layout="wide", initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)

default_url, default_key = default_settings()
# Mode deploy: jika DASHBOARD_PASSWORD diisi, dashboard dikunci dan alamat/API key TIDAK ditampilkan
# di sidebar. Nilai widget Streamlit dikirim ke browser, jadi API key tidak boleh masuk ke widget.
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")
if DASHBOARD_PASSWORD and not st.session_state.get("unlocked"):
    st.markdown('<div class="pg-head"><div class="pg-brand">PolicyGuard<span>Konsol moderasi listing</span></div></div>',
                unsafe_allow_html=True)
    login_col, _ = st.columns([1, 2])
    with login_col, st.form("login", border=False):
        pw = st.text_input("Password dashboard", type="password")
        if st.form_submit_button("Masuk", type="primary"):
            if secrets.compare_digest(pw.encode(), DASHBOARD_PASSWORD.encode()):
                st.session_state["unlocked"] = True
                st.rerun()
            st.error("Password salah.")
    st.stop()

with st.sidebar:
    if DASHBOARD_PASSWORD:
        api_url, api_key = default_url, default_key
    else:
        st.subheader("Koneksi")
        api_url = st.text_input("Alamat API", value=default_url)
        api_key = st.text_input("API key", value=default_key, type="password")
    moderator_id = st.text_input("ID moderator", value="moderator-1",
                                 help="Dicatat bersama setiap keputusan, untuk audit.")


def api(method: str, path: str, **kw):
    """Memanggil API. Mengembalikan None dan menampilkan pesan yang jelas jika gagal."""
    try:
        r = httpx.request(method, f"{api_url}{path}", headers={"X-API-Key": api_key}, timeout=30, **kw)
    except httpx.ConnectError:
        st.error(f"API tidak bisa dihubungi di {api_url}. Jalankan API dulu dengan "
                 "`python scripts/run_local.py` (atau `docker compose up`).")
        return None
    except httpx.HTTPError as e:
        st.error(f"Gagal memanggil API {path}: {e}")
        return None
    if r.status_code == 401:
        st.error("API key ditolak. Buka sidebar (tombol > di kiri atas) dan isi API key dengan salah satu "
                 "nilai SERVICE_API_KEYS dari file .env.")
        return None
    if r.status_code >= 400:
        st.error(f"API membalas HTTP {r.status_code} untuk {path}: {r.text[:300]}")
        return None
    return r.json()


@st.cache_data(ttl=300, show_spinner=False)
def load_policies(url: str, key: str) -> dict[str, str]:
    try:
        r = httpx.get(f"{url}/v1/policies", headers={"X-API-Key": key}, timeout=10)
        return {p["policy_id"]: p["title"] for p in r.json()} if r.status_code == 200 else {}
    except httpx.HTTPError:
        return {}


# ---------------------------------------------------------------- kepala halaman

try:
    health = httpx.get(f"{api_url}/health", timeout=5).json()
except Exception:
    health = None

if health:
    mode = "tanpa AI (rules saja)" if health["pipeline_mode"] == "rules_only" else "AI"
    ok = health["status"] == "ok"
    env_html = (f'<span>Mode <b>{mode}</b></span>'
                + (f'<span>Model <b>{html.escape(health.get("model", "-"))}</b></span>' if health["pipeline_mode"] == "llm" else "")
                + f'<span>Versi kebijakan <b>{health["policy_version"].removeprefix("sha256:")[:8]}</b></span>'
                + f'<span><i class="dot" style="background:{"#0CA30C" if ok else "#FAB219"}"></i>'
                  f'API {"terhubung" if ok else "terhubung, sebagian komponen bermasalah"}</span>')
else:
    env_html = '<span><i class="dot" style="background:#D03B3B"></i>API tidak terhubung</span>'

st.markdown(f'<div class="pg-head"><div class="pg-brand">PolicyGuard<span>Konsol moderasi listing</span></div>'
            f'<div class="pg-env">{env_html}</div></div>', unsafe_allow_html=True)

stats = api("GET", "/v1/stats")
if stats is None:
    st.stop()

total = stats["total_checks"]
by_dec = stats["by_decision"]
queue = api("GET", "/v1/checks", params={"decision": "needs_review", "unreviewed": True, "limit": 200}) or []
auto_rate = f"{(by_dec.get('approve', 0) + by_dec.get('reject', 0)) / total:.0%}" if total else "-"
kpis = [(len(queue), "Menunggu review"), (auto_rate, "Diputuskan otomatis"), (by_dec.get("reject", 0), "Ditolak otomatis"),
        (by_dec.get("approve", 0), "Disetujui otomatis"), (f'{stats["avg_latency_ms"]} ms', "Latensi rata-rata")]
st.markdown('<div class="pg-kpis">' + "".join(
    f'<div class="pg-kpi"><div class="v">{v}</div><div class="l">{l}</div></div>' for v, l in kpis) + "</div>",
    unsafe_allow_html=True)

tab_queue, tab_history, tab_stats = st.tabs([f"Antrian review ({len(queue)})", "Riwayat", "Statistik"])

# ---------------------------------------------------------------- tab: antrian

with tab_queue:
    if not queue:
        st.markdown('<div class="empty-state"><p>Antrian kosong. Semua listing sudah diputuskan.</p>'
                    '<p>Untuk mengirim listing contoh, jalankan <code>python scripts/smoke_test_api.py</code> '
                    'atau <code>python scripts/seed_demo.py</code>, lalu muat ulang halaman ini.</p></div>',
                    unsafe_allow_html=True)
    else:
        by_id = {c["check_id"]: c for c in queue}
        ids = list(by_id)
        if st.session_state.get("selected") not in by_id:
            st.session_state["selected"] = ids[0]
        left, right = st.columns([0.36, 0.64], gap="large")

        with left:
            st.caption("Urut dari yang paling lama menunggu.")
            with st.container(key="queue", height=640, border=False):
                st.radio("Listing menunggu keputusan", ids, key="selected", label_visibility="collapsed",
                         format_func=lambda cid: by_id[cid]["input"]["title"],
                         captions=[f'{REASONS.get(by_id[cid]["review_reason"], (by_id[cid]["review_reason"],))[0]}, '
                                   f'{by_id[cid]["input"]["category"]}, {rupiah(by_id[cid]["input"]["price"])}'
                                   for cid in ids])

        c = by_id[st.session_state["selected"]]
        listing = c["input"]
        with right:
            evidence = c["violations"] + c.get("ai_suggestions", [])
            title_spans = find_spans(listing["title"], c["rule_hits"], evidence)
            desc = listing.get("description") or ""
            desc_spans = find_spans(desc, c["rule_hits"], evidence)
            all_spans = title_spans + desc_spans
            legend = []
            if any(s[2] == "strong" for s in all_spans):
                legend.append('<span><mark class="hl-strong">stabilo</mark> bagian yang dinilai melanggar (rules keras atau AI)</span>')
            if any(s[2] == "soft" for s in all_spans):
                legend.append('<span><mark class="hl-soft">garis stabilo</mark> kata berisiko, belum tentu melanggar</span>')

            hits = "".join(f'<span class="chip">{html.escape(h["term"])} <span class="muted">{short_policy(h["policy_id"])}, '
                           f'{"keras" if h["kind"] == "hard" else "soft"}</span></span>' for h in c["rule_hits"]) \
                or '<span class="muted">Tidak ada</span>'
            retrieved = "".join(f'<span class="chip pen">{short_policy(p)}</span>' for p in c["retrieved_policy_ids"]) \
                or '<span class="muted">Tidak ada. Pada mode tanpa AI, retrieval tidak dijalankan.</span>'
            verdicts = {"violating": "melanggar", "compliant": "patuh", "insufficient_info": "informasi kurang"}
            if c["confidence"] is None:
                conf = '<span class="muted">Belum dinilai AI.</span>'
            else:
                conf = (f'Menurut AI: <b>{verdicts.get(c.get("verdict"), "-")}</b>'
                        f'<div class="meter"><i style="width:{c["confidence"] * 100:.0f}%"></i></div>'
                        f'<span class="muted">Keyakinan {c["confidence"]:.2f} dari 1,00</span>')
                for sug in c.get("ai_suggestions", []):
                    conf += (f'<p class="sug"><b>{short_policy(sug["policy_id"])}</b> '
                             f'{html.escape(sug["reason"])}</p>')
            errs = (f'<div class="llm-err">Jawaban AI ditolak validator: {html.escape("; ".join(c["llm_errors"]))}</div>'
                    if c["llm_errors"] else "")

            st.markdown(f"""
<div class="case">
  <div class="case-top">
    <div class="case-id">Listing {html.escape(c["listing_id"])}, diperiksa {ago(c["created_at"])}</div>
    <div class="verdict" style="color:{STATUS["needs_review"][1]}"><i class="dot" style="background:{STATUS["needs_review"][0]}"></i>Perlu review</div>
  </div>
  <div class="meta"><span>Kategori <b>{html.escape(listing["category"])}</b></span><span>Harga <b>{rupiah(listing["price"])}</b></span>
    <span>Diputuskan oleh <b>{DECIDED_BY.get(c["decided_by"], c["decided_by"])}</b></span></div>
  <div class="why">{REASONS.get(c["review_reason"], ("", c["review_reason"] or ""))[1]}</div>
  <div class="doc">
    <p class="t">{highlighted(listing["title"], title_spans)}</p>
    {f'<p class="d">{highlighted(desc, desc_spans)}</p>' if desc else '<p class="empty">Seller tidak menulis deskripsi.</p>'}
  </div>
  {f'<div class="legend">{"".join(legend)}</div>' if legend else ""}
  <div class="signals">
    <div><h4>Cocok dengan rules</h4>{hits}</div>
    <div><h4>Pasal yang diberikan ke AI</h4>{retrieved}</div>
    <div><h4>Penilaian AI</h4>{conf}</div>
  </div>
  {errs}
</div>""", unsafe_allow_html=True)

            policies = load_policies(api_url, api_key)
            suggested = sorted({h["policy_id"] for h in c["rule_hits"]} | {v["policy_id"] for v in evidence})
            st.markdown('<div style="height:.75rem"></div>', unsafe_allow_html=True)
            st.markdown("##### Keputusan Anda")
            with st.form(f"decide-{c['check_id']}", border=False):
                chosen = st.multiselect("Pasal yang dilanggar (wajib jika menolak)", options=list(policies) or suggested,
                                        default=[p for p in suggested if p in policies or not policies],
                                        format_func=lambda p: f"{p}  {policies.get(p, '')}")
                note = st.text_area("Catatan untuk audit (opsional)", height=80)
                b1, b2, _ = st.columns([1, 1, 2])
                approve = b1.form_submit_button("Setujui listing", key="btn_approve", use_container_width=True)
                reject = b2.form_submit_button("Tolak listing", key="btn_reject", use_container_width=True)
            if approve or reject:
                if reject and not chosen:
                    st.error("Pilih minimal satu pasal untuk menolak listing.")
                else:
                    body = {"moderator_id": moderator_id, "final_decision": "approve" if approve else "reject",
                            "policy_ids": chosen if reject else [], "note": note}
                    if api("POST", f"/v1/checks/{c['check_id']}/review", json=body):
                        st.toast(f'"{listing["title"]}" {"disetujui" if approve else "ditolak"}.')
                        st.session_state.pop("selected", None)
                        st.rerun()

# ---------------------------------------------------------------- tab: riwayat

with tab_history:
    rows = api("GET", "/v1/checks", params={"order": "newest", "limit": 200}) or []
    if not rows:
        st.markdown('<div class="empty-state"><p>Belum ada listing yang diperiksa.</p></div>', unsafe_allow_html=True)
    else:
        df = pd.DataFrame([{
            "Waktu": datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")).astimezone().strftime("%d %b %H:%M"),
            "Listing": r["input"]["title"],
            "Keputusan sistem": DECISIONS[r["decision"]],
            "Oleh": DECIDED_BY.get(r["decided_by"], r["decided_by"]),
            "Pasal": ", ".join(short_policy(v["policy_id"]) for v in r["violations"]),
            "Alasan review": REASONS.get(r["review_reason"], ("",))[0] if r["review_reason"] else "",
            "Keputusan moderator": DECISIONS.get(r["final_decision"], "") if r["final_decision"] else "",
            "Latensi (ms)": r["latency_ms"],
        } for r in rows])
        text_color = {DECISIONS[k]: v[1] for k, v in STATUS.items()}
        styled = df.style.map(lambda v: f"color: {text_color[v]}; font-weight: 600" if v in text_color else "",
                              subset=["Keputusan sistem", "Keputusan moderator"])
        st.caption(f"{len(rows)} pemeriksaan terbaru.")
        st.dataframe(styled, hide_index=True, use_container_width=True, height=min(38 + 35 * len(df), 640))

# ---------------------------------------------------------------- tab: statistik

def hbar(data: pd.DataFrame, colors: list[str] | None = None) -> alt.Chart:
    """Bar horizontal tipis dengan label nilai langsung; sumbu disembunyikan karena nilai sudah tertulis."""
    n = len(data)
    base = alt.Chart(data).encode(
        y=alt.Y("label:N", sort=None, title=None,
                axis=alt.Axis(labelColor="#596572", labelFontSize=13, ticks=False, domain=False, labelPadding=8,
                              labelLimit=260)),
        tooltip=[alt.Tooltip("label:N", title="Kategori"), alt.Tooltip("n:Q", title="Jumlah"),
                 alt.Tooltip("pct:Q", title="Persentase", format=".0%")])
    color = (alt.Color("label:N", scale=alt.Scale(domain=list(data["label"]), range=colors), legend=None)
             if colors else alt.value(SERIES))
    bars = base.mark_bar(height=14, cornerRadiusEnd=4).encode(
        x=alt.X("n:Q", title=None, axis=None, scale=alt.Scale(domainMin=0)), color=color)
    labels = base.mark_text(align="left", dx=6, color="#18222D", fontSize=13).encode(
        x="n:Q", text=alt.Text("text:N"))
    return (bars + labels).properties(height=34 * n + 10).configure_view(strokeWidth=0).configure(
        font="Public Sans, sans-serif", background="transparent")


def frame(counts: dict[str, int], names: dict[str, str]) -> pd.DataFrame:
    total_n = sum(counts.values()) or 1
    rows_ = [{"key": k, "label": names.get(k, k), "n": v, "pct": v / total_n} for k, v in counts.items()]
    df_ = pd.DataFrame(rows_)
    df_["text"] = df_.apply(lambda r: f'{r["n"]}  ({r["pct"]:.0%})', axis=1)
    return df_


with tab_stats:
    if not total:
        st.markdown('<div class="empty-state"><p>Belum ada data.</p></div>', unsafe_allow_html=True)
    else:
        st.caption(f"Dari {total} pemeriksaan sejak database dibuat. Keputusan moderator: {stats['reviews']}. "
                   f"Token terpakai: {stats['prompt_tokens'] + stats['completion_tokens']:,}".replace(",", "."))
        col1, col2 = st.columns(2, gap="large")
        with col1:
            st.markdown("##### Keputusan sistem")
            order = [k for k in ("approve", "needs_review", "reject") if k in by_dec]
            d = frame({k: by_dec[k] for k in order}, DECISIONS)
            st.altair_chart(hbar(d, [STATUS[k][0] for k in order]), use_container_width=True)
        with col2:
            st.markdown("##### Siapa yang memutuskan")
            st.altair_chart(hbar(frame(stats["by_decided_by"], DECIDED_BY)), use_container_width=True)
        reasons = {k: v for k, v in sorted(stats["by_review_reason"].items(), key=lambda kv: -kv[1]) if k != "-"}
        st.markdown("##### Alasan listing dikirim ke moderator")
        if reasons:
            st.altair_chart(hbar(frame(reasons, {k: v[0] for k, v in REASONS.items()})), use_container_width=True)
        else:
            st.caption("Belum ada listing yang dikirim ke moderator.")
