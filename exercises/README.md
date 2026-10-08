# Latihan Debugging

Tujuan: membangun kebiasaan debugging yang tidak Anda dapat karena menerima kode yang sudah jadi.
Setiap latihan memasang **satu** bug. Anda menemukan dan memperbaikinya sendiri.

## Cara kerja

```bash
git init && git add . && git commit -m "baseline"   # sekali saja
python exercises/break.py 1                           # pasang bug 1
python -m pytest -q                                   # lihat gejala
# ... cari dan perbaiki ...
python -m pytest -q                                   # pastikan semua lolos
git diff                                              # bandingkan dengan kode asli
git checkout -- .                                     # bersihkan sebelum latihan berikutnya
```

Aturan: jangan membuka `break.py` dan jangan langsung membaca `git diff` sebelum menemukan penyebabnya.
Buka petunjuk satu per satu hanya jika buntu.

Setelah setiap latihan, jawab tiga pertanyaan secara tertulis:
1. Apa gejala yang terlihat oleh **pengguna** (moderator, seller, atau tim ops), bukan oleh test?
2. Bagaimana Anda akan mendeteksi bug ini di production **tanpa** test? (log, metrik, atau kolom DB mana?)
3. Test mana yang menangkapnya, dan kenapa test itu ada?

---

## Latihan 1: Moderator heran

**Laporan dari tim ops:** "Akhir-akhir ini ada listing 'Kopi herbal, sembuhkan diabetes' yang langsung tayang. Padahal kata 'sembuhkan' ada di daftar rule."

<details><summary>Petunjuk 1</summary>Listing ini tidak terkena hard rule. Keputusannya diambil di tabel keputusan.</details>
<details><summary>Petunjuk 2</summary>Baris mana di tabel keputusan yang seharusnya menangkap "LLM bilang patuh, tapi rule soft tidak setuju"?</details>
<details><summary>Petunjuk 3</summary>Buka ai/router.py, baca baris 8 dengan teliti, kata per kata.</details>

## Latihan 2: Kebijakan baru tidak berlaku

**Laporan dari policy team:** "Kami sudah memperbarui pasal kemarin, tapi listing yang dikirim ulang dengan teks yang sama tetap mendapat keputusan lama."

<details><summary>Petunjuk 1</summary>Keputusan lama yang dipakai ulang berasal dari mana? Lihat kolom `cached` di respons.</details>
<details><summary>Petunjuk 2</summary>Apa saja yang seharusnya membuat cache tidak terpakai? (ADR-011, system_design bagian 5)</details>
<details><summary>Petunjuk 3</summary>Bandingkan fungsi pembuat kunci cache dengan desain di system_design bagian 5.</details>

## Latihan 3: Lonjakan `invalid_llm_output`

**Laporan dari monitoring:** metrik `policyguard_llm_invalid_output_total` naik tajam, antrian moderator membengkak dengan alasan `invalid_llm_output`, dan biaya token naik. Kolom `llm_errors` di database berisi "evidence tidak ditemukan di listing", padahal kutipannya terlihat ada di judul listing.

<details><summary>Petunjuk 1</summary>Bandingkan evidence dari LLM dengan judul listing huruf per huruf. Apa bedanya?</details>
<details><summary>Petunjuk 2</summary>Kenapa biaya token ikut naik? (Apa yang dilakukan pipeline saat output tidak valid?)</details>
<details><summary>Petunjuk 3</summary>Lihat pemeriksaan nomor 5 di ai/validator.py.</details>

## Latihan 4: Buku sejarah ditolak

**Laporan dari seller:** "Listing 'Buku sejarah perjudian di Nusantara' saya ditolak otomatis."

<details><summary>Petunjuk 1</summary>`decided_by` pada keputusan itu bernilai `rule`. Rule mana yang cocok?</details>
<details><summary>Petunjuk 2</summary>Apakah "judi" benar-benar muncul sebagai kata di judul itu, atau hanya sebagai bagian dari kata lain?</details>
<details><summary>Petunjuk 3</summary>Lihat cara regex rule dibuat di RuleEngine.__init__.</details>

## Latihan 5: Gangguan 10 menit yang tidak pernah selesai

**Laporan:** API OpenAI sempat mati 10 menit pagi tadi. Sejak itu, beberapa listing yang dikirim ulang oleh seller lain dengan teks yang sama terus masuk `needs_review` dengan alasan `llm_unavailable`, padahal LLM sudah normal kembali.

<details><summary>Petunjuk 1</summary>Kalau LLM sudah normal, kenapa LLM tidak dipanggil? Lihat kolom `cached`.</details>
<details><summary>Petunjuk 2</summary>Hasil seperti apa yang tidak boleh dipakai ulang sebagai cache? (system_design bagian 5)</details>
<details><summary>Petunjuk 3</summary>Lihat query pencarian cache di app/db/repository.py.</details>

## Latihan 6 (tanpa bug): trade-off daftar rule

Ini bukan bug, tapi keputusan desain. Tambahkan `"pistol": "POL-WPN-01"` ke bagian `soft` di `data/rules/rules.json`, lalu jalankan:

```bash
python -m ai.evaluation.run_eval --split dev --mode rules_only
```

Bandingkan `automation_rate` dan baris `keyword_false_positive` dengan hasil tanpa perubahan ini
(hasil awal ada di docs/eval_rules_only_dev.md). Jawab:
1. Listing mana yang berubah keputusannya, dan kenapa?
2. Di mode `llm`, apa akibatnya bagi beban moderator? (Ingat baris 8 tabel keputusan.)
3. Kapan menambah istilah ke soft list layak dilakukan?
