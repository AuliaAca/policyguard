# Decision Log

Format: konteks → keputusan → alasan → alternatif yang ditolak → konsekuensi.
Keputusan bisa diubah, tapi perubahannya harus dicatat sebagai ADR baru.

---

## ADR-001: FastAPI untuk API layer
- **Keputusan:** FastAPI.
- **Alasan:** validasi request/response bawaan lewat Pydantic, mendukung async untuk panggilan LLM yang I/O-bound, dokumentasi API otomatis.
- **Alternatif ditolak:** Flask (validasi harus dibuat manual), Django (terlalu banyak fitur yang tidak dipakai).
- **Konsekuensi:** schema Pydantic yang sama dipakai untuk API dan untuk memvalidasi output LLM.

## ADR-002: Satu database (PostgreSQL + pgvector)
- **Keputusan:** data relasional dan vektor di PostgreSQL yang sama.
- **Alasan:** jumlah pasal kebijakan kecil (puluhan sampai ratusan chunk). Satu database berarti satu sistem untuk dijalankan, di-backup, dan di-debug.
- **Alternatif ditolak:** vector database terpisah. Bermanfaat pada jutaan vektor, tapi menambah satu komponen tanpa manfaat di skala ini.
- **Konsekuensi:** jika jumlah vektor tumbuh sangat besar, keputusan ini ditinjau ulang.

## ADR-003: Tanpa agent dan tanpa LangChain di inti pipeline
- **Keputusan:** orchestrator ditulis dengan Python biasa.
- **Alasan:** urutan langkah selalu sama dan diketahui sejak awal. Agent cocok saat langkah ditentukan saat runtime; di sini agent hanya menambah latency, biaya, dan ketidakpastian. Menulis manual juga membuat setiap langkah bisa dijelaskan dan di-debug.
- **Alternatif ditolak:** agent dengan tool calling; multi-agent.
- **Konsekuensi:** di Phase 12, opsional membuat versi LangGraph untuk membandingkan trade-off secara nyata.

## ADR-004: Fail-safe ke `needs_review`, dikembalikan sebagai HTTP 200
- **Keputusan:** kegagalan komponen AI menghasilkan `needs_review`, bukan approve dan bukan error HTTP.
- **Alasan:** "tidak tahu" tidak boleh diperlakukan sebagai "aman". Auto-approve saat gagal juga membuka celah: seller bisa sengaja memicu kegagalan. Hasil `needs_review` adalah keputusan yang valid bagi pemanggil, sehingga dikembalikan sebagai 200 dengan `review_reason`.
- **Alternatif ditolak:** auto-approve saat gagal; mengembalikan 503 saat LLM gagal (membuat sistem listing harus menangani kegagalan AI sendiri).
- **Konsekuensi:** gangguan LLM yang lama menambah antrian moderator. Perlu dimonitor (Phase 10). Kebijakan per kategori untuk kondisi ini adalah keputusan bisnis yang dibahas dengan ops.

## ADR-005: Batas panjang di kontrak API, tanpa pemotongan diam-diam
- **Konteks:** pemotongan deskripsi membuat LLM menilai teks yang tidak lengkap dan bisa menjawab "patuh" dengan yakin tanpa tanda apa pun.
- **Keputusan:** deskripsi maksimal 5.000 karakter; lebih dari itu ditolak dengan 422. Teks yang lolos validasi dikirim utuh ke LLM.
- **Alasan:** kegagalan yang terlihat (422) lebih aman daripada kegagalan yang diam. Angka 5.000 adalah pilihan project. Dalam integrasi nyata, batas ini harus ≥ batas deskripsi di sistem listing agar listing sah tidak tertolak.
- **Alternatif ditolak:** memotong deskripsi; mengirim teks panjang tanpa batas (biaya dan latency tidak terkendali).
- **Konsekuensi:** rule prefilter tetap membaca teks penuh. Jika kelak batas harus dinaikkan, pertimbangkan memilih bagian teks yang paling relevan dengan embeddings, bukan memotong dari depan.

## ADR-006: Cache di tabel `checks`, bukan di Redis
- **Keputusan:** hasil pemeriksaan dicari ulang lewat index `cache_key` di PostgreSQL.
- **Alasan:** semua hasil sudah disimpan untuk audit; tabel yang sama bisa dipakai sebagai cache tanpa komponen tambahan.
- **Alternatif ditolak:** Redis cache. Lebih cepat, tapi menambah sinkronisasi data dan sumber bug baru untuk penghematan yang belum terbukti dibutuhkan.
- **Konsekuensi:** hasil `fallback` tidak pernah dipakai ulang sebagai cache.

## ADR-007: Gagal menyimpan ke DB → 503
- **Konteks:** blueprint awal menyarankan tetap mengembalikan hasil dengan penanda `persisted: false`. Keputusan itu diubah di sini.
- **Keputusan:** jika keputusan tidak bisa disimpan, kembalikan 503 dan biarkan pemanggil retry.
- **Alasan:** keputusan moderasi tanpa jejak audit tidak bisa dipertanggungjawabkan saat seller mengajukan banding. Retry aman karena endpoint idempoten.
- **Konsekuensi:** ketersediaan service bergantung pada ketersediaan DB.

## ADR-008: Threshold di config, ditetapkan dari evaluasi
- **Keputusan:** `T_REJECT` dan `T_APPROVE` adalah config, bukan konstanta di kode, dan nilainya dipilih dari data evaluasi.
- **Alasan:** confidence yang dilaporkan LLM belum tentu terkalibrasi. Threshold adalah trade-off bisnis antara precision dan beban moderator, jadi harus bisa diubah tanpa deploy kode.
- **Konsekuensi:** Phase 7 wajib menghasilkan kurva precision vs automation rate per threshold.

## ADR-009: Evidence harus muncul di teks listing
- **Keputusan:** setiap pelanggaran yang dilaporkan LLM wajib menyertakan kutipan dari listing, dan kutipan itu dicek secara deterministik.
- **Alasan:** mencegah LLM mengarang alasan; moderator bisa langsung melihat bagian listing yang bermasalah.
- **Konsekuensi:** prompt harus meminta kutipan persis. Tingkat kegagalan validasi ini dipantau.

## ADR-010: Normalisasi hanya untuk pencocokan rules
- **Keputusan:** normalisasi agresif (angka ke huruf, menghapus pemisah) hanya dipakai pada salinan teks untuk rule prefilter. LLM menerima teks asli.
- **Alasan:** normalisasi menangkap plesetan, tapi bisa merusak arti ("1mg" → "img"). LLM lebih baik melihat teks asli.
- **Konsekuensi:** aturan normalisasi diuji dengan unit test, termasuk kasus yang tidak boleh berubah.

## ADR-011: Versi kebijakan dihitung otomatis dari isi dokumen
- **Keputusan:** `policy_version` = hash isi semua dokumen kebijakan, dihitung saat ingest.
- **Alasan:** versi manual mudah lupa dinaikkan. Hash berubah otomatis setiap kali isi berubah.
- **Konsekuensi:** setiap perubahan kebijakan membatalkan cache. Ini memang perilaku yang diinginkan.

---

# Keputusan saat implementasi (Phase 4-12)

## ADR-012: Indeks kebijakan di memori, pgvector ditunda (mengubah ADR-002)
- **Konteks:** kebijakan hanya 15 pasal (15 vektor).
- **Keputusan:** embedding pasal disimpan sebagai matriks numpy di memori proses; pencarian = perkalian matriks. Tabel `policy_chunks` dari system_design tidak dibuat.
- **Alasan:** 15 vektor tidak membutuhkan database vektor. Lebih sedikit komponen = lebih sedikit titik gagal. PostgreSQL tetap dipakai untuk data relasional.
- **Konsekuensi:** setiap proses (API, setiap worker) membangun indeksnya sendiri saat pertama dipakai (15 panggilan embedding dalam satu request). Pindah ke pgvector ketika jumlah pasal mencapai ribuan, atau ketika indeks harus diperbarui tanpa restart di banyak instance.

## ADR-013: Embedding default lewat API OpenAI, model lokal opsional
- **Konteks:** rencana awal memakai sentence-transformers lokal.
- **Keputusan:** default `EMBEDDING_PROVIDER=openai`; `local` tersedia lewat requirements-local-embeddings.txt.
- **Alasan:** model lokal menarik PyTorch dan membuat image Docker sangat besar. Volume embedding di sistem ini kecil (1 query per listing + 15 pasal), sehingga biayanya kecil.
- **Konsekuensi:** retrieval bergantung pada API eksternal; jika mati, keputusan fallback ke `retrieval_unavailable` dan indeks pulih sendiri saat API kembali (diuji).

## ADR-014: Antrian batch dengan Redis list, bukan RQ/Celery
- **Keputusan:** LPUSH oleh API, BRPOP oleh worker; status item di PostgreSQL.
- **Alasan:** mekanismenya terlihat jelas dan mudah dijelaskan. Idempotensi item (status `pending` dicek sebelum diproses) membuat ID yang masuk antrian dua kali tidak diproses dua kali.
- **Konsekuensi (keterbatasan diketahui):** item yang sudah di-BRPOP lalu worker mati sebelum selesai tidak kembali ke antrian. Perbaikan: pola "reliable queue" (BLMOVE ke list processing) atau memakai RQ/Celery yang sudah menangani ini.

## ADR-015: Dua baseline pembanding untuk membuktikan nilai RAG
- **Keputusan:** evaluasi menjalankan tiga mode: `rules_only`, `llm_all` (semua pasal di prompt), `llm_rag` (top-k pasal).
- **Alasan:** dengan hanya 15 pasal, mengirim semua pasal ke LLM adalah alternatif yang masuk akal. RAG harus dibuktikan lebih baik atau lebih murah, bukan diasumsikan. Perbandingan "LLM tanpa kebijakan sama sekali" tidak dipakai karena terlalu mudah dikalahkan.
- **Konsekuensi:** jika `llm_all` sama baiknya dengan `llm_rag`, laporan harus menyatakannya, dan alasan memakai RAG menjadi skalabilitas (kebijakan nyata bisa ratusan pasal) dan biaya token, bukan akurasi.

## ADR-016: Dugaan AI saat ragu tetap ditampilkan ke moderator
- **Konteks:** saat AI menilai `violating` dengan confidence di bawah `T_REJECT`, router mengirim listing ke `needs_review` tanpa daftar pelanggaran. Moderator tidak melihat bagian mana yang dicurigai AI.
- **Keputusan:** endpoint detail mengembalikan `verdict` dan `ai_suggestions`, diambil dari output LLM yang sudah lolos validator. Dashboard memberi stabilo pada kutipan tersebut dan mengisi pasal yang disarankan.
- **Alasan:** pekerjaan AI yang sudah dibayar (token) tidak terbuang; moderator memutuskan lebih cepat. Karena hanya output yang lolos validasi yang ditampilkan, pasal dan kutipannya dijamin ada di listing.
- **Alternatif ditolak:** menambah kolom database baru (butuh migration; database lama pengguna akan rusak dengan `create_all`).
- **Konsekuensi:** `violations` tetap berarti "dasar keputusan otomatis"; `ai_suggestions` berarti "bahan pertimbangan". Keduanya sengaja dipisah agar audit tidak tercampur.

## ADR-017: Penolakan oleh moderator wajib menyebut pasal
- **Keputusan:** `POST /v1/checks/{id}/review` dengan `final_decision=reject` tanpa `policy_ids` ditolak (422).
- **Alasan:** konsisten dengan keputusan otomatis: setiap penolakan harus bisa dijelaskan ke seller dan diaudit.

## ADR-018: (dicadangkan)
Diisi pemilik project setelah evaluasi dev set: nilai `T_REJECT`/`T_APPROVE` yang dipilih dan alasannya (RUNBOOK Tahap 8.6).

## ADR-019: Deploy latihan sebagai satu service gratis (API + dashboard dalam satu container)
- **Konteks:** target deploy adalah Render free tier: 0,1 CPU, 512 MB RAM, filesystem sementara, server tidur setelah 15 menit tanpa trafik. Free web service tidak bisa menerima trafik jaringan privat dari service lain.
- **Keputusan:** `Dockerfile.render` menjalankan API di `127.0.0.1:8000` dan dashboard di `$PORT` dalam satu container (`deploy/render_start.py`). Database SQLite, diisi ulang dengan listing dev set setiap start. Mode `rules_only`. Dashboard dikunci `DASHBOARD_PASSWORD`, dan API key tidak pernah dimasukkan ke widget Streamlit (nilai widget dikirim ke browser).
- **Alasan:** dua service terpisah berarti API harus terbuka ke internet (karena tidak ada jaringan privat di free tier). Satu container membuat API tidak bisa diakses dari luar sama sekali. Pemakaian memori terukur sekitar 270 MB setelah dashboard dipakai.
- **Alternatif ditolak:** Render Postgres gratis (dihapus setelah 30 hari); dua service publik (API terbuka); mode AI di deploy publik (pengunjung bisa menghabiskan saldo OpenAI).
- **Konsekuensi:** keputusan moderator hilang saat server tidur. Ini deploy untuk latihan dan demo, bukan production. Untuk production: service terpisah di jaringan privat, Postgres terkelola, Redis + worker, dan autentikasi pengguna sungguhan.
