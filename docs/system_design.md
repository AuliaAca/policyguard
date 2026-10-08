# PolicyGuard: System Design (Phase 2)

Dokumen ini adalah referensi teknis. Alasan di balik setiap keputusan ada di `decision_log.md` (ADR-xxx).

---

## 1. Kontrak API

### `POST /v1/checks`: memeriksa satu listing (sync)

**Header:** `X-API-Key: <key>`

**Request body**

| Field | Tipe | Aturan validasi |
|---|---|---|
| `listing_id` | string | wajib, 1–64 karakter; ID dari sistem listing, dipakai untuk idempotensi |
| `title` | string | wajib, 5–200 karakter |
| `description` | string | opsional, maksimal 5.000 karakter (ADR-005) |
| `category` | enum | wajib, salah satu kategori yang terdaftar di config |
| `price` | integer | wajib, > 0, dalam Rupiah |

**Response `200`**

```json
{
  "check_id": "uuid",
  "listing_id": "L016",
  "decision": "reject",
  "violations": [
    {
      "policy_id": "POL-DRG-01",
      "evidence": "alpr4 1mg",
      "reason": "Menjual obat psikotropika dengan nama disamarkan"
    }
  ],
  "review_reason": null,
  "decided_by": "llm",
  "versions": {
    "policy": "sha256:ab12...",
    "prompt": "judge-v1",
    "model": "<nama model>"
  },
  "cached": false,
  "latency_ms": 1840
}
```

- `decision`: `approve` | `reject` | `needs_review`
- `decided_by`: `rule` | `llm` | `fallback`
- `review_reason` (hanya jika `needs_review`): `low_confidence` | `insufficient_info` | `rule_llm_disagree` | `llm_unavailable` | `invalid_llm_output` | `retrieval_unavailable`

**Status code**

| Code | Kapan | Catatan |
|---|---|---|
| `200` | Keputusan berhasil dibuat **dan disimpan** | Termasuk `needs_review` karena LLM gagal. Itu hasil yang valid, bukan error HTTP (ADR-004). |
| `401` | API key tidak ada atau salah | |
| `422` | Body tidak valid (field kurang, deskripsi > 5.000 karakter, kategori tidak dikenal) | LLM tidak dipanggil |
| `503` | Database tidak bisa diakses, keputusan tidak tersimpan | Pemanggil boleh retry; aman karena idempoten (ADR-007) |
| `500` | Bug yang tidak terduga | Dicatat dengan `request_id` |

### Endpoint lain

| Endpoint | Fungsi | Phase |
|---|---|---|
| `GET /v1/checks/{check_id}` | Membaca satu hasil pemeriksaan | 4 |
| `POST /v1/checks/{check_id}/review` | Moderator menyimpan keputusan final; reject wajib menyebut pasal (ADR-017) | 4 |
| `GET /v1/checks` | Antrian (`order=oldest`) atau riwayat (`order=newest`); detail berisi `ai_suggestions` (ADR-016) | 10 |
| `GET /v1/policies` | Daftar pasal untuk dashboard | 10 |
| `GET /health` | Status service, DB, dan model embedding | 4 |
| `GET /metrics` | Metrik Prometheus | 10 |
| `POST /v1/batches`, `GET /v1/batches/{id}` | Pemeriksaan banyak listing secara async | 12 |

---

## 2. Pipeline keputusan

```text
Request
  │
  ▼
[1] Validasi (Pydantic) ──── gagal ──► 422
  │
  ▼
[2] Idempotensi: listing_id + content_hash sudah ada? ──── ya ──► kembalikan check yang sama
  │
  ▼
[3] Cache lookup (cache_key) ──── hit ──► kembalikan hasil (cached=true)
  │
  ▼
[4] Rule prefilter pada teks PENUH yang dinormalisasi
  │      hard hit ──► reject (decided_by=rule)
  │      soft hit ──► dicatat sebagai sinyal
  ▼
[5] Retrieval: top-k pasal kebijakan ──── gagal ──► needs_review (retrieval_unavailable)
  │
  ▼
[6] Bangun prompt (listing utuh, tanpa pemotongan)
  │
  ▼
[7] LLM Judge (timeout + retry) ──── gagal ──► needs_review (llm_unavailable)
  │
  ▼
[8] Validasi output ──── invalid 2x ──► needs_review (invalid_llm_output)
  │
  ▼
[9] Decision router (tabel di bawah)
  │
  ▼
[10] Simpan ke DB ──── gagal ──► 503
  │
  ▼
Response 200 + log + metrik
```

### Tabel keputusan (Decision Router)

Dievaluasi dari atas ke bawah; aturan pertama yang cocok dipakai.

| # | Kondisi | Keputusan | `review_reason` |
|---|---|---|---|
| 1 | Rule hard hit | `reject` | |
| 2 | Retrieval gagal | `needs_review` | `retrieval_unavailable` |
| 3 | LLM gagal setelah retry | `needs_review` | `llm_unavailable` |
| 4 | Output LLM invalid setelah 1x perbaikan | `needs_review` | `invalid_llm_output` |
| 5 | LLM: `insufficient_info` | `needs_review` | `insufficient_info` |
| 6 | LLM: `violating`, confidence ≥ `T_REJECT` | `reject` | |
| 7 | LLM: `violating`, confidence < `T_REJECT` | `needs_review` | `low_confidence` |
| 8 | LLM: `compliant`, ada rule soft hit | `needs_review` | `rule_llm_disagree` |
| 9 | LLM: `compliant`, confidence ≥ `T_APPROVE` | `approve` | |
| 10 | Selain itu | `needs_review` | `low_confidence` |

`T_REJECT` dan `T_APPROVE` disimpan di config dan ditetapkan dari hasil evaluasi di Phase 7 (ADR-008). Tidak ada nilai default yang dianggap benar sebelum diukur.

---

## 3. Rule prefilter

- Berjalan pada **teks penuh**: judul + deskripsi.
- Normalisasi khusus pencocokan (pada salinan teks, ADR-010):
  - Unicode NFKC, huruf kecil
  - Substitusi angka-ke-huruf hanya di dalam token yang mencampur huruf dan angka (`alpr4` → `alpra`), tidak pada token angka murni atau satuan (`1mg` tetap)
  - Pemisah di antara huruf dihapus (`x.a.n.a.x` → `xanax`)
- Dua daftar istilah, disimpan sebagai data (bukan di dalam kode):
  - **hard**: istilah yang hampir pasti melanggar di konteks apa pun → reject langsung
  - **soft**: istilah berisiko tinggi yang bisa sah di konteks tertentu → sinyal untuk router
- Istilah umum seperti "pistol" **tidak** dimasukkan ke soft list. Kalau dimasukkan, setiap "pistol air mainan" akan masuk review dan automation rate turun. Daftar soft dievaluasi ulang di Phase 7.

Batas yang diakui: rules hanya menangkap pola yang sudah diketahui. Variasi baru ditangani LLM, dan keputusan moderator dipakai untuk menambah daftar.

---

## 4. LLM Judge

### Output yang diminta (structured output)

```json
{
  "verdict": "compliant | violating | insufficient_info",
  "violations": [
    {"policy_id": "POL-xxx-00", "evidence": "kutipan persis dari listing", "reason": "..."}
  ],
  "confidence": 0.0
}
```

### Validasi output (kode biasa, bukan AI)

1. JSON sesuai schema (Pydantic).
2. `verdict = violating` ⇒ minimal 1 violation. `verdict = compliant` ⇒ 0 violation.
3. Setiap `policy_id` **harus ada di pasal hasil retrieval** untuk request ini.
4. Setiap `evidence` **harus benar-benar muncul** di teks listing (pencocokan string setelah normalisasi spasi dan huruf kecil) (ADR-009).
5. `confidence` di rentang 0–1.

Gagal validasi → 1x panggilan ulang dengan pesan error validasi → masih gagal → `needs_review`.

### Pertahanan terhadap prompt injection

Teks listing adalah input yang tidak dipercaya. Pertahanan berlapis, tidak ada yang sempurna sendirian:

- Listing dibungkus pembatas yang jelas, dengan instruksi bahwa isinya adalah data, bukan perintah.
- Output dibatasi schema; LLM tidak bisa "menjawab bebas".
- Rule hard hit diputuskan **sebelum** LLM, jadi LLM tidak bisa membatalkannya.
- Validator menolak kutipan pasal atau evidence yang dikarang.
- Dataset evaluasi memuat contoh listing berisi upaya injection.

---

## 5. Cache dan idempotensi

### Kunci

```text
content_hash = sha256(normalisasi(title) | normalisasi(description) | category | price)
cache_key    = sha256(content_hash | policy_version | prompt_version | model)
```

- `price` ikut dalam hash karena harga memengaruhi penilaian (misalnya barang bermerek dengan harga jauh di bawah pasar).
- `policy_version` = hash isi seluruh dokumen kebijakan, dihitung otomatis saat ingest (ADR-011). Mengubah satu kata di kebijakan menghasilkan versi baru.

### Aturan

- Cache disimpan di tabel `checks` (index pada `cache_key`), bukan di Redis (ADR-006).
- **Hasil fallback tidak di-cache.** Keputusan dengan `decided_by = fallback` tidak boleh dipakai ulang. Jika di-cache, gangguan LLM selama 10 menit akan "membeku" menjadi `needs_review` permanen untuk listing tersebut.
- Idempotensi: request dengan `listing_id` + `content_hash` yang sama mengembalikan `check` yang sudah ada. Ini membuat retry dari pemanggil aman.

### Batas cache

Cache hanya mencegah hasil basi untuk **listing yang dikirim ulang**. Listing yang sudah tayang tidak dicek ulang ketika kebijakan berubah. Itu ditangani oleh pemindaian ulang batch (Phase 12).

---

## 6. Data model (PostgreSQL + pgvector)

### `policy_chunks` (tidak dibuat; lihat ADR-012)

> Saat implementasi, indeks kebijakan disimpan di memori. Tabel ini dibuat jika pindah ke pgvector.

| Kolom | Tipe | Keterangan |
|---|---|---|
| id | serial PK | |
| policy_id | text | contoh: `POL-DRG-01` |
| policy_version | text | hash dokumen saat ingest |
| heading | text | judul pasal |
| content | text | isi pasal |
| embedding | vector(N) | N mengikuti model embedding yang dipilih di Phase 6 |

### `checks`
| Kolom | Tipe | Keterangan |
|---|---|---|
| id | uuid PK | `check_id` |
| listing_id | text | |
| content_hash | text | index bersama `listing_id` (idempotensi) |
| cache_key | text | index |
| input | jsonb | salinan request |
| decision | text | approve / reject / needs_review |
| decided_by | text | rule / llm / fallback |
| review_reason | text null | |
| violations | jsonb | |
| rule_hits | jsonb | hard dan soft |
| retrieved_policy_ids | text[] | untuk evaluasi retrieval |
| llm_raw_output | jsonb null | untuk debugging |
| policy_version, prompt_version, model | text | |
| prompt_tokens, completion_tokens | int null | untuk biaya |
| latency_ms | int | |
| created_at | timestamptz | |

### `reviews`
| Kolom | Tipe | Keterangan |
|---|---|---|
| id | uuid PK | |
| check_id | uuid FK → checks | |
| moderator_id | text | |
| final_decision | text | approve / reject |
| policy_ids | text[] | |
| note | text | |
| created_at | timestamptz | |

Tabel `batches` dan `batch_items` ditambahkan di Phase 12.

---

## 7. Konfigurasi (environment variables)

| Variabel | Contoh | Rahasia? |
|---|---|---|
| `DATABASE_URL` | `postgresql://...` | Ya |
| `OPENAI_API_KEY` | | Ya |
| `SERVICE_API_KEYS` | daftar key pemanggil | Ya |
| `LLM_MODEL` | nama model | Tidak |
| `LLM_TIMEOUT_SECONDS` | | Tidak |
| `LLM_MAX_RETRIES` | | Tidak |
| `RETRIEVAL_TOP_K` | | Tidak |
| `T_REJECT`, `T_APPROVE` | diisi setelah Phase 7 | Tidak |
| `PROMPT_VERSION` | `judge-v1` | Tidak |

Rahasia hanya ada di `.env` lokal (masuk `.gitignore`). Repository hanya berisi `.env.example` tanpa nilai rahasia.

---

## 8. Ringkasan mode kegagalan

| Kegagalan | Perilaku | Terlihat di |
|---|---|---|
| Input tidak valid | `422`, LLM tidak dipanggil | log, metrik 4xx |
| Rule list gagal dimuat | Service gagal start (lebih baik gagal jelas daripada jalan tanpa rules) | log startup, `/health` |
| Retrieval gagal | `needs_review` (`retrieval_unavailable`) | log, metrik fallback |
| LLM timeout / 429 / 5xx | Retry dengan backoff, lalu `needs_review` (`llm_unavailable`) | log, metrik fallback |
| Output LLM invalid | 1x perbaikan, lalu `needs_review` (`invalid_llm_output`) | log, `llm_raw_output` di DB |
| DB gagal menyimpan | `503`, pemanggil retry | log, metrik 5xx |
| Bug tak terduga | `500` dengan `request_id` | log dengan stack trace |
