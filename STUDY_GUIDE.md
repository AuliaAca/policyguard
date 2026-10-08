# Study Guide

Panduan ini untuk Anda, pemilik project, bukan untuk pembaca repository. Tujuannya: Anda mampu menjelaskan, menjalankan, dan men-debug setiap bagian penting **tanpa membaca README**.

## 0. Cara memakai panduan ini

Urutan yang disarankan:
1. Jalankan test dan API lokal (bagian 1). Jangan lanjut sebelum keduanya berjalan di laptop Anda.
2. Ikuti satu request dari awal sampai akhir (bagian 2), sambil membuka file yang disebut.
3. Baca tabel per file (bagian 3). Fokus pada yang bertanda **MUST UNDERSTAND** dan **MUST DEBUG**.
4. Kerjakan latihan debugging di `exercises/`.
5. Jalankan evaluasi sungguhan (bagian 8). Ini satu-satunya cara mendapat angka untuk portfolio.
6. Interview simulation.

---

## 1. Jalankan dulu

Ikuti RUNBOOK.md bagian "Cara tercepat: jalankan dari VS Code", atau Tahap 0 sampai 6. Lewat terminal, intinya:
```
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/make_env.py local
python scripts/run_local.py
```
Lalu buka `http://localhost:8000/docs` dan `http://localhost:8501`.

Cara belajar paling efektif: jalankan lewat VS Code (F5), pasang breakpoint di `ai/pipeline.py` fungsi `run`, lalu kirim satu listing. Ikuti eksekusinya baris demi baris sambil membaca bagian 2 di bawah.

---

## 2. Perjalanan satu request

Request: `POST /v1/checks` dengan listing "Kopi herbal, bisa sembuhkan diabetes".

| # | Terjadi di | Apa yang terjadi | Jika gagal |
|---|---|---|---|
| 1 | `app/main.py` middleware `request_context` | Membuat `request_id`, mulai stopwatch | – |
| 2 | `app/api/deps.py` `require_api_key` | Cek header `X-API-Key` | 401 |
| 3 | `app/schemas/api.py` `ListingIn` | Validasi panjang, kategori, harga | 422, LLM tidak dipanggil |
| 4 | `app/api/routes_checks.py` `create_check` | Ubah ke `Listing`, panggil service | – |
| 5 | `app/services/check_service.py` `check` | Hitung `content_hash` dan `cache_key` | – |
| 6 | `repository.find_by_idempotency_key` | Request ini pernah datang? Kembalikan check lama | DB mati → 503 |
| 7 | `repository.find_cached` | Isi + versi sama dari listing lain? Salin hasilnya (`cached=true`) | – |
| 8 | `ai/pipeline.py` `run` → `ai/rules.py` `match` | Normalisasi teks, cocokkan rules. "sembuhkan" = soft hit | File rules rusak → service gagal start |
| 9 | `ai/retrieval.py` `retrieve` | Embed listing, ambil 5 pasal paling mirip (POL-HLT-01 teratas) | `retrieval_unavailable` |
| 10 | `ai/prompts/judge_v1.py` `build_messages` | Susun prompt: instruksi + pasal + listing di dalam `<listing>` | – |
| 11 | `ai/llm.py` `OpenAIJudge.complete` | Panggil model dengan structured output; SDK menangani timeout dan retry | `llm_unavailable` |
| 12 | `ai/validator.py` `validate_output` | JSON valid? pasal ada di yang diberikan? evidence ada di listing? | 1x perbaikan, lalu `invalid_llm_output` |
| 13 | `ai/router.py` `route` | Tabel keputusan: violating + confidence ≥ T_REJECT → reject | – |
| 14 | `check_service._save` | Simpan semua jejak ke tabel `checks` | 503 (ADR-007) |
| 15 | `app/core/metrics.py` | Counter keputusan, fallback, token; histogram latency | Tidak boleh menggagalkan request |
| 16 | middleware | Tambah header `x-request-id`, catat latency HTTP | – |

**Bagian yang AI hanya langkah 9 (embedding) dan 11 (LLM).** Semua langkah lain adalah pemrograman biasa yang deterministik. Ini poin penting untuk interview.

---

## 3. Peta file

Kategori:
- **MU** (MUST UNDERSTAND): business logic dan arsitektur. Harus bisa dijelaskan baris per baris.
- **SU** (SHOULD UNDERSTAND): pahami konsep dan alasannya.
- **CR** (CAN REFERENCE): kode library/framework. Tidak perlu dihafal.
- **MBD** (MUST BE ABLE TO DEBUG): bagian yang paling mungkin rusak; harus bisa troubleshoot sendiri.

### Komponen AI (`ai/`)

| File | Kategori | Jawaban jika interviewer bertanya "file ini untuk apa?" |
|---|---|---|
| `pipeline.py` | **MU, MBD** | "Urutan pemeriksaan satu listing: rules, retrieval, LLM, validasi, router. Sengaja tanpa database dan HTTP, sehingga API, worker, dan script evaluasi memakai logika yang sama persis. Hard rule langsung reject supaya LLM tidak dipanggil. Semua kegagalan berakhir di needs_review." |
| `router.py` | **MU** | "Tabel keputusan. LLM hanya memberi verdict dan confidence; file ini yang memutuskan berdasarkan threshold. Setiap baris punya satu test. Baris 8 menangani ketidaksepakatan rule dan LLM." |
| `validator.py` | **MU, MBD** | "Pemeriksaan deterministik atas output LLM: format, konsistensi verdict, pasal harus berasal dari pasal yang diberikan, dan kutipan bukti harus benar-benar ada di listing. Ini pertahanan halusinasi yang tidak bergantung pada AI." |
| `rules.py` | **MU, MBD** | "Prefilter keyword yang murah. Normalisasi menangkap plesetan seperti alpr4 dan s-l-o-t, tapi tidak mengubah satuan seperti 1mg. Regex memakai batas kata supaya 'judi' tidak cocok di 'perjudian'. Hard = langsung reject, soft = sinyal." |
| `prompts/judge_v1.py` | **MU** | "Instruksi ke LLM. Teks seller dibungkus tag listing dan dinyatakan tidak terpercaya untuk mengurangi prompt injection. Versi prompt ikut di kunci cache." |
| `retrieval.py` | **SU, MBD** | "Embedding pasal disimpan di memori; query = embedding listing; skor = cosine similarity lewat perkalian matriks. Mode 'all' untuk baseline. Jika API embedding gagal, indeks dicoba dibangun lagi di request berikutnya." |
| `llm.py` | **SU** | "Satu-satunya tempat memanggil model. Memaksa output JSON dengan schema strict. Semua error API diubah menjadi LLMUnavailable agar pipeline bisa fail-safe." |
| `policies.py` | **SU** | "Memecah dokumen kebijakan per pasal, dan menghitung versi kebijakan dari hash isinya." |
| `factory.py` | **SU** | "Merakit pipeline dari konfigurasi. Satu tempat, supaya API, worker, dan evaluasi tidak berbeda konfigurasi." |
| `types.py` | **SU** | "Struktur data bersama antar-komponen." |
| `evaluation/metrics.py` | **MU** | "Definisi metrik. Recall menghitung reject DAN needs_review sebagai tertangkap. Threshold sweep mensimulasikan ulang keputusan tanpa memanggil LLM lagi." |
| `evaluation/run_eval.py` | **SU** | "Menjalankan pipeline ke dataset dan menulis laporan. Menolak test set tanpa --final dan tanpa label yang sudah direview." |

### Backend (`app/`, `worker/`)

| File | Kategori | Jawaban |
|---|---|---|
| `services/check_service.py` | **MU, MBD** | "Membungkus pipeline dengan kebutuhan production: idempotensi, cache, penyimpanan, metrik. Price dan versi ikut di hash. Hasil fallback tidak di-cache. Race condition dua request identik ditangani lewat unique constraint." |
| `services/batch_service.py` | **MU, MBD** | "API menyimpan batch lalu memasukkan ID item ke Redis list. Worker mengambil satu per satu. Push dilakukan sebelum commit agar batch tidak tersimpan setengah. Item yang sudah diproses dilewati." |
| `schemas/api.py` | **MU** | "Kontrak API. Validasi terjadi sebelum kode lain berjalan; batas 5.000 karakter tanpa pemotongan diam-diam (ADR-005)." |
| `db/models.py` | **SU** | "Tabel checks, reviews, batches, batch_items. Unique constraint (listing_id, content_hash) untuk idempotensi; index cache_key untuk pencarian cache." |
| `db/repository.py` | **SU, MBD** | "Semua query. find_cached mengecualikan hasil fallback." |
| `main.py` | **SU** | "Merakit aplikasi saat startup, middleware request_id dan latency, serta mapping exception ke 503/404/500. Menolak start tanpa API key." |
| `core/config.py` | **SU** | "Semua konfigurasi dari environment. Rahasia memakai SecretStr agar tidak tercetak di log." |
| `core/logging.py` | **SU** | "Log JSON dengan request_id untuk melacak satu request." |
| `core/metrics.py` | **SU** | "Metrik Prometheus: keputusan, fallback, token, latency." |
| `api/deps.py` | **SU** | "Autentikasi API key dengan compare_digest." |
| `api/routes_*.py` | **CR** | "Handler tipis: terima request, panggil service, ubah ke schema respons." |
| `worker/worker.py` | **SU** | "Loop BRPOP. Berhenti dengan rapi saat SIGTERM. Bisa dijalankan beberapa instance." |
| `dashboard/app.py` | **SU** | "Konsol moderator; hanya memanggil API, tidak menyentuh database. Bagian `find_spans` memberi stabilo pada kata yang cocok dengan rules (memakai normalisasi yang sama dengan `ai/rules.py`) dan kutipan dari AI. Dugaan AI saat ragu (`ai_suggestions`) ditampilkan sebagai bahan pertimbangan, terpisah dari `violations` (ADR-016)." |
| `deploy/render_start.py`, `Dockerfile.render`, `render.yaml` | **SU** | "Deploy satu service gratis: API di 127.0.0.1 (tidak terbuka ke internet), dashboard di port publik dengan password, data contoh diisi ulang setiap start. Alasannya di ADR-019." |
| `scripts/make_env.py`, `scripts/run_local.py` | **CR** | "Alat bantu menjalankan project: membuat .env dan menyalakan API + dashboard sekaligus." |

### Data dan test

| File | Kategori | Catatan |
|---|---|---|
| `data/policies/listing_policy.md` | **MU** | Isi yang dibaca LLM. Ubah = versi kebijakan baru = cache tidak terpakai. |
| `data/rules/rules.json` | **MU** | Baca bagian `_catatan`. |
| `tests/conftest.py` | **SU** | FakeJudge dan FakeRetriever: kenapa sistem bisa diuji tanpa API. |
| `tests/test_openai_mock.py` | **SU** | Membuktikan format request/response OpenAI, bukan kualitas model. |

---

## 4. Komponen AI secara mendalam

### Apa yang dilakukan LLM
Membaca listing dan beberapa pasal, lalu menghasilkan: verdict, daftar pelanggaran (pasal + kutipan + alasan), dan confidence.

### Apa yang TIDAK dilakukan LLM
- Tidak memutuskan approve/reject. Router yang memutuskan.
- Tidak memilih pasal dari seluruh kebijakan. Retrieval yang memilih kandidat.
- Tidak menyimpan, men-cache, atau mencatat apa pun.
- Tidak "tahu" kebijakan kita. Semua aturan dikirim di prompt.
- Tidak dipercaya. Setiap output divalidasi.

### Kapan memakai apa (dan jawaban untuk project ini)

| Teknik | Kapan dipakai | Di project ini |
|---|---|---|
| Prompt engineering | Mengatur perilaku dan format output | Ya: aturan penilaian, pertahanan injection, structured output |
| Embeddings | Mencari teks yang maknanya mirip | Ya: memilih pasal yang relevan |
| RAG | Model butuh pengetahuan yang tidak ia punya atau yang sering berubah | Ya: kebijakan internal berubah tanpa retraining. Dengan 15 pasal, keunggulannya atas "kirim semua pasal" harus dibuktikan (ADR-015) |
| Tool calling | Model perlu memilih aksi atau data tambahan saat runtime | Tidak: semua data yang dibutuhkan sudah ada di request |
| Agent | Langkah tidak bisa ditentukan sebelumnya | Tidak: urutan langkah selalu sama |
| Multi-agent | Beberapa peran dengan konteks berbeda harus bekerja sama | Tidak: menambah biaya, latency, dan ketidakpastian tanpa manfaat |
| Fine-tuning | Perilaku tidak bisa dicapai lewat prompt, data berlabel banyak | Tidak: kebijakan berubah, data sedikit |

---

## 5. Production thinking: di mana di kode?

| Pertanyaan | Jawaban dan lokasi |
|---|---|
| Bagaimana API menangani error? | 401 (deps.py), 422 (schemas), 503 untuk DB (check_service → main.py), 404, 500 dengan request_id |
| Bagaimana model failure ditangani? | llm.py → LLMUnavailable → router baris 3 → needs_review |
| Output LLM salah? | validator.py → 1x perbaikan → invalid_llm_output |
| Data failure? | Input divalidasi schema; dataset divalidasi `scripts/validate_dataset.py` |
| Latency diukur di mana? | Histogram HTTP (middleware), histogram pipeline, `latency_ms` per check, p50/p95 di evaluasi |
| Biaya dipantau bagaimana? | Token per check di DB, counter token di /metrics, biaya per 1.000 listing di evaluasi |
| Scale bagaimana? | API stateless → tambah instance; worker → `--scale worker=N`; batasnya rate limit API LLM dan koneksi DB |
| Secrets? | `.env` (di .gitignore), SecretStr, `.env.example` tanpa nilai |
| Docker? | Satu image untuk API dan worker; compose menyatukan Postgres, Redis, dashboard |

---

## 6. Keterbatasan yang diketahui (sampaikan dengan jujur jika ditanya)

1. **Dataset sintetis, sebagian besar ditulis AI.** Angka evaluasi kemungkinan lebih tinggi daripada di data nyata.
2. **Rules ditulis sambil mengetahui dataset.** Baseline rules_only terlalu optimis.
3. **Confidence LLM belum tentu terkalibrasi.** Threshold dipilih dari data, tapi dengan sampel kecil.
4. **Antrian batch bisa kehilangan item** jika worker mati setelah BRPOP (ADR-014).
5. **Tanpa migration database** (create_all). Perubahan tabel di production butuh Alembic.
6. **Setiap proses membangun indeks embedding sendiri** (ADR-012).
7. **Evidence dari hard rule adalah istilah ternormalisasi** ("alpra"), bukan kutipan persis dari listing.
8. **Dashboard memuat sampai 200 listing per tab** tanpa paginasi. Cukup untuk demo, tidak untuk antrian production. (Masalah N+1 query di endpoint list sudah diperbaiki: status review diambil dalam satu query.)
9. **Tidak ada rate limiting** di API.
10. **Hanya teks.** Foto tidak dinilai.
11. **Integrasi OpenAI belum diuji dengan API asli.**

---

## 7. Playbook debugging

| Gejala | Lihat di mana |
|---|---|
| Banyak `needs_review` tiba-tiba | `GET /v1/stats` → `by_review_reason`. `llm_unavailable` → cek log "LLM tidak tersedia" (nama error: 401 = API key, 404/400 = nama model, 429 = rate limit). `invalid_llm_output` → kolom `llm_errors` di tabel checks |
| Listing melanggar lolos | Kolom `retrieved_policy_ids`: pasal yang benar ikut terambil? Jika tidak → masalah retrieval. Jika ya → lihat `llm_raw_output` dan `confidence` |
| Listing patuh ditolak | `decided_by`: `rule` → istilah mana di `rule_hits`; `llm` → lihat `violations[].evidence` |
| `/health` degraded | Field `checks` menunjukkan komponen yang gagal |
| Batch tidak selesai | Apakah worker berjalan? `redis-cli LLEN policyguard:batch_items`; kolom `error` dan `attempts` di batch_items |
| Melacak satu request | Ambil header `x-request-id`, cari di log |

---

## 8. Yang harus Anda kerjakan untuk menyelesaikan project

1. **Jalankan lokal** (bagian 1).
2. **Siapkan API key OpenAI** dan cek nama model yang tersedia. Isi harga token dari halaman harga resmi saat menjalankan evaluasi.
3. **Evaluasi di dev set**, tiga mode: `rules_only`, `llm_all`, `llm_rag`.
4. **Analisis kesalahan:** buka laporan, baca listing di `missed_violations` dan `false_rejects` satu per satu. Tulis penyebabnya (retrieval? prompt? label salah?).
5. **Perbaiki prompt jika perlu** (naikkan `PROMPT_VERSION`) dan ulangi di dev. Jangan pernah memakai test set untuk ini.
6. **Pilih threshold** dari tabel "Simulasi threshold" di laporan dev. Catat alasannya sebagai ADR baru.
7. **Review 147 label test set** dan ubah `label_status` menjadi `reviewed` di `data/eval/listings.jsonl`, lalu jalankan `python scripts/split_dataset.py data/eval/listings.jsonl data/eval`.
8. **Evaluasi final sekali:** `--split test --mode llm_rag --final`. Angka ini yang masuk portfolio, apa pun hasilnya.
9. **Jalankan `docker compose up --build`** di laptop Anda dan perbaiki jika ada masalah.
10. **Kerjakan `exercises/`.**
11. **Isi tabel hasil di README** dengan angka nyata.

Langkah 3 sampai 8 adalah bukti terkuat untuk requirement "analyze data, support model testing, evaluate performance". Tanpa langkah ini, project belum punya bukti kualitas.
