# Policy Changelog

Changelog sengaja disimpan di luar `data/policies/`. Semua file di folder itu akan di-chunk dan dikirim ke LLM; catatan perubahan bukan aturan dan tidak boleh ikut terambil saat retrieval.

## v1 (Phase 3)

**File:** `data/policies/policy_draft_v0.md` diganti nama menjadi `data/policies/listing_policy.md`. Versi tidak lagi ditulis di nama file karena `policy_version` dihitung dari hash isi (ADR-011).

**Struktur:** setiap pasal kini memakai format yang sama: Larangan, Contoh, Tidak termasuk, Alasan kebijakan (jika ada), Konteks hukum.

**Pasal baru:** POL-TOB-01, POL-ALC-01, POL-COS-01, POL-DAT-01, POL-GAM-01, POL-DOC-01, POL-ADT-01.

**Pasal diubah:**
- POL-HLT-02: cakupan diperluas ke kosmetik ("putih permanen dalam 3 hari").
- Semua pasal lama: ditambah bagian "Tidak termasuk".

**Dampak ke label:** tidak ada label seed v0 yang berubah. Validasi ulang dijalankan dengan `scripts/validate_dataset.py`.

## Celah kebijakan yang diketahui

| Celah | Dampak | Penanganan sementara |
|---|---|---|
| POL-IP-01 tidak mengatur harga sebagai sinyal barang tiruan | Listing bermerek dengan harga janggal tanpa istilah tiruan tidak bisa dipastikan | Label `compliant` + `insufficient_info` (pedoman aturan 9) |
| POL-COS-01 hanya menilai bahan yang disebut di listing | Kosmetik berbahaya yang tidak menyebut bahannya tidak tertangkap dari teks | Di luar scope teks; dicatat sebagai keterbatasan |
| POL-GAM-01 merujuk UU ITE Pasal 27 ayat (2) dari sumber yang membahas perubahan tahun 2016 | UU ITE telah diubah lagi pada 2024; penomoran pasal belum diverifikasi ulang | Verifikasi ke teks resmi sebelum dipakai sebagai rujukan formal |
