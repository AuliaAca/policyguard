# Labeling Guideline

## Untuk siapa dan untuk apa

Pedoman ini dipakai oleh **pelabel dataset evaluasi** PolicyGuard. Label yang dihasilkan adalah *ground truth* untuk **mengevaluasi** sistem. Dataset ini **tidak dipakai untuk melatih** model apa pun.

Pedoman ini tidak mengatur perilaku sistem (misalnya validasi output LLM atau kapan listing dikirim ke moderator). Itu ada di `system_design.md`.

Dokumen kebijakan yang dirujuk: `data/policies/listing_policy.md`. Jika kebijakan berubah, label yang terdampak harus ditinjau ulang.

---

## Format label

| Field | Isi |
|---|---|
| `label` | `compliant` atau `violating`. Tidak ada nilai lain. |
| `violations` | Daftar `{policy_id, evidence}`. Wajib berisi minimal 1 item jika `violating`, kosong jika `compliant`. |
| `insufficient_info` | `true` hanya untuk kondisi di aturan 6. Default `false`. |
| `note` | Alasan singkat yang merujuk pasal atau aturan pedoman ini. |

"Review manual" **bukan label**. Itu perilaku sistem, bukan kebenaran tentang listing.

---

## Aturan

### 1. Dasar penilaian adalah dokumen kebijakan
Setiap label `violating` harus merujuk ID pasal yang ada di dokumen kebijakan. Bukan intuisi, bukan hukum, bukan kebijakan marketplace lain.

Jika pelabel tidak setuju dengan suatu pasal, yang diubah adalah **kebijakannya** (dan perubahannya dicatat), bukan membuat pengecualian saat melabeli.

### 2. Hanya isi record yang dinilai
Yang dinilai hanya: judul, deskripsi, kategori, dan harga. Foto tidak termasuk scope. Pengetahuan dari luar tentang seller tertentu tidak dipakai.

### 3. Yang dinilai adalah listing, bukan hanya produk
- Produk yang boleh dijual tetap `violating` jika listing-nya memuat klaim terlarang. Contoh: L014 kopi herbal + "sembuhkan diabetes" → POL-HLT-01.
- Produk yang dilarang tetap `violating` walaupun deskripsinya sopan. Contoh: L012 burung parkit → POL-ANM-01.

### 4. Klaim dinilai berdasarkan jenisnya, bukan bisa atau tidaknya diverifikasi
- Klaim yang termasuk jenis terlarang di pasal tetap melanggar, **dengan atau tanpa bukti** yang disebut seller. Contoh: "sembuhkan kanker" → POL-HLT-01.
- Klaim yang tidak dilarang tidak membuat listing melanggar, walaupun tidak bisa diverifikasi. Contoh: "untuk relaksasi" (L006).
- Klaim positif seller ("BPOM terdaftar", "izin edar resmi", "ori", "berizin") **tidak dipakai sebagai bukti kepatuhan**. Listing dinilai seolah klaim itu tidak ada.

### 5. Plesetan dinilai sama dengan istilah aslinya
Nama yang disamarkan dengan angka, singkatan, atau pemisah dinilai sama dengan istilah aslinya. Contoh: "alpr4" = alprazolam (L016) → POL-DRG-01.

### 6. `insufficient_info` hanya untuk sinyal yang tidak bisa dipastikan
Gunakan `insufficient_info: true` **hanya jika** listing memiliki sinyal konkret ke arah pelanggaran, tetapi teks tidak cukup untuk memastikannya. Label utamanya tetap `compliant`.

- Deskripsi singkat tanpa sinyal risiko **bukan** `insufficient_info`. Labelnya `compliant`. Contoh: L007 "Sepatu sneakers brand lokal, ukuran 42".
- "Barang bisa saja palsu" **bukan** sinyal. Setiap barang bermerek bisa palsu; jika itu dianggap sinyal, semua barang bermerek akan masuk kategori ini.

### 7. Satu listing bisa melanggar lebih dari satu pasal
Catat semua pasal yang dilanggar. Contoh: L002 kakatua raja → POL-ANM-01 (hewan hidup) dan POL-ANM-02 (satwa dilindungi).

### 8. Evidence adalah kutipan persis dari listing
Untuk setiap pelanggaran, catat kutipan **persis** dari judul atau deskripsi yang menjadi dasar pelanggaran. Pilih kutipan sependek mungkin yang masih cukup menjelaskan pelanggaran.

Kutipan ini dipakai untuk menilai apakah evidence yang diberikan sistem tepat.

### 9. Barang tiruan (POL-IP-01)
| Kondisi | Label |
|---|---|
| Menyebut merek pihak lain **dan** memakai istilah tiruan ("KW", "replika", "mirror", "1:1", "grade ori") | `violating` |
| Menyebut merek pihak lain, tanpa istilah tiruan, harga wajar | `compliant` |
| Menyebut merek pihak lain, tanpa istilah tiruan, harga jauh di bawah kewajaran untuk merek itu | `compliant` + `insufficient_info: true` |
| Tidak menyebut merek pihak lain | Tidak ada sinyal barang tiruan |

Baris ketiga adalah **celah kebijakan**: POL-IP-01 belum mengatur harga sebagai sinyal. Sampai kebijakan diputuskan, kasus ini diberi `insufficient_info` dan dicatat.

### 10. Senjata dan mainan (POL-WPN-01, POL-WPN-02)
- Senjata api, amunisi, bagian senjata api → `violating` POL-WPN-01.
- Airsoft gun, pistol angin, senapan angin → `violating` POL-WPN-02. Tidak ada pengecualian "ambigu" untuk kategori ini; kebijakannya eksplisit.
- Mainan yang jelas bukan replika fungsional, serta produk yang hanya bermotif senjata → `compliant`. Contoh: L008 pistol air mainan, L019 kaos motif pistol.

### 11. Jika pelabel ragu
Keraguan berarti kebijakan atau pedoman kurang jelas. Langkahnya:
1. Tulis `PERLU KLARIFIKASI: <alasan>` di `note`.
2. Jangan masukkan listing itu ke test set.
3. Perjelas kebijakan atau pedoman, lalu beri label.

### 12. Konsistensi
- Kasus yang sejenis harus mendapat label yang sama. Contoh: L005 dan L014 sama-sama klaim menyembuhkan penyakit → keduanya `violating` POL-HLT-01.
- Setiap aturan baru diuji ke seed data sebelum dipakai. Jika ada konflik, ubah aturannya atau ubah labelnya, lalu catat alasannya.
- Setelah beberapa hari, labeli ulang sekitar 10% sampel tanpa melihat label lama. Label yang berubah menandakan aturan yang kurang jelas.
