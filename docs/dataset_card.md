# Dataset Card: PolicyGuard Evaluation Set

## Isi

| File | Isi |
|---|---|
| `data/eval/listings.jsonl` | Master: 250 listing berlabel. Satu-satunya sumber kebenaran. |
| `data/eval/dev.jsonl` | 101 listing untuk memperbaiki prompt dan threshold. |
| `data/eval/test.jsonl` | 147 listing, dipakai **sekali** di akhir untuk angka akhir. |
| `data/eval/excluded.jsonl` | 2 listing berstatus `PERLU KLARIFIKASI`; tidak dipakai sampai kebijakan diperjelas. |

`dev.jsonl`, `test.jsonl`, dan `excluded.jsonl` dihasilkan oleh `scripts/split_dataset.py`. Jangan diedit manual; ubah master lalu jalankan ulang script.

## Asal data dan status label

- Semua listing **sintetis**. Tidak ada data seller atau listing nyata.
- 15 listing awal ditulis oleh pemilik project; sisanya ditulis dengan bantuan AI (Claude) dan dilabeli berdasarkan `docs/labeling_guideline.md`.
- Semua label berstatus `draft`. Sebelum test set dipakai, setiap listing di `test.jsonl` harus ditinjau manusia dan `label_status` diubah menjadi `reviewed` di master.

Konsekuensi yang harus dinyatakan saat melaporkan hasil: listing yang ditulis AI cenderung lebih "rapi" daripada listing nyata (ejaan konsisten, pelanggaran tertulis eksplisit). Angka evaluasi di dataset ini kemungkinan lebih tinggi daripada di data production.

## Komposisi

- 140 `violating`, 110 `compliant`. Proporsi ini **sengaja** diperkaya pelanggaran agar setiap pasal punya 8–14 contoh. Di production, sebagian besar listing patuh.
- Karena proporsinya berbeda dari production, **precision di dataset ini akan lebih tinggi daripada di production**. Recall per pasal lebih bisa dipercaya karena tidak bergantung pada proporsi.
- `test_tag` menandai jenis kesulitan: `keyword_false_positive` (35), `keyword_false_negative` (16), `hard_negative` (18), `prompt_injection` (4), `seller_claim_ignored` (5), `multi_policy` (4), `insufficient_info` (8), `policy_gap` (2).

## Cara pembagian

- Rasio dev 40% / test 60%, stratified per pasal utama (atau per tipe untuk listing patuh).
- Pembagian per `group`: listing yang mirip (misalnya semua listing alprazolam/Xanax) selalu berada di split yang sama.
- Deterministik: urutan memakai hash dengan seed tetap, sehingga hasil split selalu sama.

## Keterbatasan

- `data/rules/rules.json` ditulis oleh pihak yang sama yang menulis dataset, sambil mengetahui isinya (termasuk test set). Akibatnya baseline `rules_only` terlihat lebih baik daripada keyword filter sungguhan: precision 1.0 dan tidak ada salah tolak di dev set bukan bukti bahwa keyword cukup.

- Test set hanya berisi 5–10 pelanggaran per pasal. Selisih satu listing menggeser recall per pasal sebesar 10–20 poin persen. Angka per pasal harus dilaporkan bersama jumlah contohnya.
- Hanya teks; tidak ada foto.
- Fakta hukum di kebijakan diverifikasi saat ditulis; lihat `docs/policy_changelog.md` untuk hal yang belum terverifikasi.
