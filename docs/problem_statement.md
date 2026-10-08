# Problem Statement: PolicyGuard

## Konteks

Marketplace menerima listing baru dalam jumlah besar setiap hari (asumsi project; angka pasti tidak tersedia). Setiap listing harus sesuai dengan **kebijakan marketplace** sebelum tayang.

Kebijakan marketplace bisa lebih ketat daripada hukum. Karena itu sistem ini menilai **kepatuhan terhadap kebijakan**, bukan legalitas menurut hukum.

## User dan Stakeholder

| Pihak | Peran terhadap sistem | Kebutuhan |
|---|---|---|
| **Moderator** (user utama) | Meninjau listing yang dikirim sistem | Hanya meninjau kasus yang benar-benar tidak pasti, lengkap dengan pasal kebijakan dan alasan |
| **Policy team** | Menulis dan memperbarui dokumen kebijakan | Perubahan kebijakan berlaku tanpa perubahan kode atau retraining model |
| **Engineering** (sistem listing) | Memanggil API sistem ini | Kontrak API yang stabil, latency yang dapat diprediksi, perilaku yang jelas saat gagal |
| **Seller** (terdampak, bukan user) | Pemilik listing | Tidak ditolak secara salah; alasan penolakan jelas |
| **Buyer** (terdampak, bukan user) | Pembeli | Tidak menemukan listing yang melanggar kebijakan |

## Masalah (asumsi kondisi saat ini)

1. **Review manual tidak skala.** Volume listing tumbuh lebih cepat daripada kapasitas moderator, sehingga antrian review menjadi lambat.
2. **Filter keyword tidak memahami konteks.**
   - *False positive*: listing yang patuh ditolak karena mengandung kata tertentu ("pistol air mainan anak", "pisau dapur").
   - *False negative*: pelanggaran lolos karena seller memakai plesetan atau istilah lain ("alpr4", "mirror quality" sebagai ganti "KW").
3. **Kebijakan berubah.** Daftar keyword harus diperbarui manual, dan classifier ML klasik harus dilatih ulang dengan data berlabel baru setiap kali kebijakan berubah.
4. **Keputusan sulit dijelaskan.** Penolakan tanpa rujukan pasal sulit diaudit oleh moderator dan sulit dipahami oleh seller.

## Scope

### Yang dilakukan sistem
- Menilai **teks** listing (judul, deskripsi, kategori, harga) terhadap dokumen kebijakan.
- Mengembalikan keputusan: `approve`, `reject`, atau `needs_review`.
- Untuk `reject`: menyebut **ID pasal kebijakan** yang dilanggar beserta alasannya.
- Mengirim kasus yang tidak pasti, dan kasus saat sistem mengalami kegagalan, ke moderator.
- Menyimpan setiap keputusan untuk audit.

### Yang tidak dilakukan sistem
- Tidak menganalisis foto produk (future improvement).
- Tidak memverifikasi klaim seller (nomor izin edar, keaslian barang, izin kepemilikan).
- Tidak menilai legalitas dan tidak membuat keputusan hukum.
- Tidak menggantikan moderator. Kasus yang tidak pasti tetap diputuskan manusia.
- Tidak menjamin bebas kesalahan.

## Prinsip Keputusan

- **Fail-safe:** jika sistem ragu atau salah satu komponen gagal, listing dikirim ke `needs_review`. Sistem tidak pernah melakukan auto-approve dalam kondisi gagal.
- **Keputusan berbasis pasal:** setiap `reject` harus merujuk pasal kebijakan yang benar-benar ada.

## Indikator Keberhasilan

### A. Diukur dalam project (pada test set berlabel)

| Metrik | Definisi | Kenapa penting |
|---|---|---|
| Recall pelanggaran | Dari semua listing yang melanggar, berapa persen tidak lolos (`reject` atau `needs_review`) | Pelanggaran yang lolos adalah risiko terbesar |
| Precision reject | Dari semua listing yang di-`reject`, berapa persen benar-benar melanggar | Penolakan yang salah merugikan seller |
| Automation rate | Persentase listing yang diputuskan tanpa moderator | Mengukur beban kerja yang berkurang |
| Citation validity | Persentase `reject` yang mengutip pasal yang benar | Keputusan harus bisa diaudit |
| Latency p95 | Waktu proses untuk 95% request | Sistem listing butuh waktu respons yang dapat diprediksi |
| Biaya per 1.000 listing | Biaya API LLM | Kelayakan ekonomi |

Accuracy **tidak** dipakai sebagai metrik utama. Data moderasi tidak seimbang: sebagian besar listing patuh. Sistem yang meng-approve semua listing bisa memperoleh accuracy tinggi tanpa menangkap satu pun pelanggaran.

Target angka untuk setiap metrik ditetapkan setelah baseline diukur.

### B. Diukur jika sistem di-deploy (tidak diklaim dalam project ini)
- Waktu moderasi rata-rata per listing.
- Jumlah listing yang masuk review manual per hari.
- Jumlah komplain seller terkait penolakan.
- Jumlah laporan buyer atas listing melanggar yang lolos.
