# Runbook: menjalankan PolicyGuard langkah demi langkah

## Cara membaca panduan ini

- **Kotak berlabel "Ketik"**: salin **seluruh** isi kotak, tempel ke terminal, tekan **Enter**. Jika kotak berisi beberapa baris, Anda boleh menempel semuanya sekaligus.
- **Kotak berlabel "Yang muncul"**: contoh output. **Jangan diketik.** Angka acak (ID, API key, waktu) akan berbeda di komputer Anda.
- Jika ada dua versi (**Windows** dan **macOS/Linux**), pakai salah satu saja sesuai komputer Anda.
- Tidak ada bagian perintah yang perlu diubah, **kecuali** yang ditulis jelas dengan kata **GANTI**.
- Jangan lanjut ke tahap berikutnya jika hasilnya tidak sesuai "Yang muncul". Salin seluruh pesan error, bukan hanya baris terakhir.

Ringkasan tahap:

| Tahap | Isi | Butuh API key OpenAI? | Butuh Docker? |
|---|---|---|---|
| VS Code / 0–6 | Install, test, jalankan API + dashboard | Tidak | Tidak |
| 7 | Evaluasi tanpa AI | Tidak | Tidak |
| 8 | Mode AI dan evaluasi dengan LLM | Ya | Tidak |
| 9–10 | Review label dan evaluasi final | Ya | Tidak |
| 11 | Docker Compose | Opsional | Ya |
| 12–13 | Latihan debugging, upload ke GitHub | Tidak | Tidak |
| 14 | Deploy ke internet (Render, gratis) | Tidak | Tidak (Render yang build) |

---

## Cara tercepat: jalankan dari VS Code

Project ini sudah berisi pengaturan VS Code di folder `.vscode/`. Jika memakai VS Code, Anda bisa mengikuti bagian ini dan melewati Tahap 1 sampai 6 di bawah.

**A. Buka project**
1. Buka VS Code → **File → Open Folder** → pilih folder `policyguard` → klik **Yes, I trust the authors** jika ditanya.
2. Jika muncul tawaran memasang ekstensi yang direkomendasikan (Python, Python Debugger), klik **Install**. Jika tidak muncul: buka panel Extensions (Ctrl+Shift+X, macOS: Cmd+Shift+X), cari **Python** dari Microsoft, klik Install.

**B. Buat virtual environment dan install library (sekali saja)**
1. Tekan **Ctrl+Shift+P** (macOS: **Cmd+Shift+P**), ketik `Python: Create Environment`, tekan Enter.
2. Pilih **Venv**.
3. Pilih Python 3.11 atau lebih baru.
4. Saat ditanya file dependency, centang **requirements-dev.txt**, lalu klik OK.
5. Tunggu beberapa menit sampai notifikasi selesai di kanan bawah. Folder `.venv` akan muncul di panel kiri.

Jika `Python: Create Environment` tidak muncul, ekstensi Python belum terpasang (kembali ke A.2).

**C. Buat file `.env`**
1. Menu **Terminal → Run Task...**
2. Pilih **PolicyGuard: buat .env (tanpa AI)**.

Yang muncul di panel terminal bawah:
```text
.env ditulis untuk mode 'local' (tanpa AI).
  API key (untuk halaman /docs): dev-...
```

**D. Jalankan test**
1. Klik ikon **labu (Testing)** di bilah kiri.
2. Klik tombol **Run Tests** (ikon segitiga ganda) di bagian atas panel.

Yang muncul: semua test bertanda centang hijau. Alternatif: **Terminal → Run Task... → PolicyGuard: jalankan semua test**, hasilnya `61 passed`.

**E. Nyalakan API dan dashboard**
1. Klik ikon **Run and Debug** di bilah kiri (segitiga dengan serangga), atau tekan Ctrl+Shift+D.
2. Di dropdown paling atas panel, pilih **PolicyGuard: API + Dashboard**.
3. Klik tombol hijau ▶ di sebelahnya (atau tekan **F5**).

Yang terjadi: dua terminal terbuka (API dan Dashboard), lalu browser terbuka otomatis ke `http://localhost:8501`. Jika browser tidak terbuka, buka alamat itu sendiri.

**F. Isi dashboard dengan listing contoh**
1. Di dropdown Run and Debug, pilih **Kirim listing contoh (seed_demo)**, lalu klik ▶.
2. Kembali ke browser, tekan **F5** untuk memuat ulang. Antrian review berisi listing yang perlu diputuskan.

**G. Matikan**
Klik tombol kotak merah **Stop** di toolbar debug di atas editor. API dan dashboard berhenti bersama.

**Bonus untuk belajar:** karena dijalankan lewat debugger, Anda bisa memasang *breakpoint*. Buka `ai/pipeline.py`, klik di sebelah kiri nomor baris di dalam fungsi `run` sampai muncul titik merah, lalu kirim listing (langkah F). Eksekusi berhenti di baris itu, dan Anda bisa melihat isi variabel `hits`, `retrieved`, dan `decision` di panel kiri. Ini cara terbaik memahami alur satu request.

---

## Tahap 0: Buka terminal di folder project

1. Ekstrak `policyguard.zip`.
2. **Cara termudah:** buka aplikasi **VS Code** → menu **File → Open Folder** → pilih folder `policyguard` → menu **Terminal → New Terminal**. Terminal di bagian bawah VS Code otomatis berada di folder project.

Cara lain (tanpa VS Code):

**Windows**: buka menu Start, ketik `PowerShell`, buka. Lalu ketik (GANTI path dengan lokasi folder Anda):
```powershell
cd C:\Users\NamaAnda\Downloads\policyguard
```

**macOS/Linux**: buka aplikasi Terminal. Lalu ketik (GANTI path dengan lokasi folder Anda):
```bash
cd ~/Downloads/policyguard
```

Cek bahwa Anda di folder yang benar. Ketik:
```
python --version
```
Yang muncul: `Python 3.11.x`, `3.12.x`, atau `3.13.x`.

- Windows: jika yang muncul jendela Microsoft Store atau "not recognized", install Python dari python.org dan centang **"Add python.exe to PATH"** saat install. Tutup lalu buka lagi terminal.
- macOS: jika `python` tidak ditemukan, pakai `python3` **hanya untuk Tahap 1 langkah pertama**. Setelah virtual environment aktif, `python` akan bekerja.

---

## Tahap 1: Virtual environment dan install library (sekali saja)

Virtual environment = folder `.venv` yang berisi library khusus project ini, supaya tidak tercampur dengan Python lain di komputer Anda.

**Windows**, ketik:
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```
Jika muncul error merah berisi `running scripts is disabled on this system`, ketik ini sekali, lalu ulangi baris `.venv\Scripts\Activate.ps1`:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**macOS/Linux**, ketik:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Yang muncul: awalan `(.venv)` di depan baris terminal, misalnya:
```text
(.venv) PS C:\Users\NamaAnda\Downloads\policyguard>
```

> **Penting:** setiap kali membuka terminal baru, aktifkan lagi dengan baris kedua di atas (`.venv\Scripts\Activate.ps1` atau `source .venv/bin/activate`). VS Code sering melakukannya otomatis; cek apakah `(.venv)` sudah muncul.

Install library. Ketik (sama untuk semua OS):
```
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```
Butuh beberapa menit. Yang muncul di akhir:
```text
Successfully installed ... streamlit-... fastapi-... (daftar panjang)
```
Tidak boleh ada baris yang diawali `ERROR:`.

---

## Tahap 2: Jalankan test

Ketik:
```
python -m pytest -q
```
Yang muncul:
```text
..........................................................               [100%]
61 passed in 3.12s
```
Windows: jika muncul jendela Firewall untuk Python, klik **Allow**. Salah satu test menyalakan server di komputer Anda sendiri (127.0.0.1).

---

## Tahap 3: Buat file konfigurasi `.env`

Ketik:
```
python scripts/make_env.py local
```
Yang muncul:
```text
.env ditulis untuk mode 'local' (tanpa AI).
  API key (untuk halaman /docs): dev-K9w65uTAEFbbk0Cz
  OPENAI_API_KEY               : kosong
```
Script ini membuat file `.env` berisi konfigurasi dan API key acak. Anda tidak perlu mengedit `.env` dengan tangan. Catat API key yang muncul; key ini dibutuhkan hanya jika Anda mencoba API lewat halaman `/docs` di browser.

---

## Tahap 4: Nyalakan API dan dashboard

Ketik:
```
python scripts/run_local.py
```
Yang muncul (setelah beberapa detik):
```text
============================================================
  API       : http://localhost:8000/health
  Docs API  : http://localhost:8000/docs
  Dashboard : http://localhost:8501
  Tekan Ctrl+C untuk mematikan.
============================================================
```
**Biarkan terminal ini terbuka.** Kita sebut ini **Terminal 1**. Selama menyala, terminal ini akan terus menampilkan log.

Buka di browser:

| Alamat | Yang seharusnya terlihat |
|---|---|
| http://localhost:8000/health | Teks `{"status":"ok","pipeline_mode":"rules_only",...}` |
| http://localhost:8501 | Dashboard "PolicyGuard, Konsol moderasi listing". Pojok kanan atas: titik hijau "API terhubung". Antrian masih kosong. |
| http://localhost:8000/docs | Halaman dokumentasi API interaktif |

Contoh tampilan dashboard ada di `docs/img/dashboard_antrian.png` dan `docs/img/dashboard_statistik.png`.

---

## Tahap 5: Kirim listing contoh (Terminal 2)

Buka terminal **kedua**. Di VS Code: klik ikon **+** di panel terminal. Pastikan `(.venv)` muncul; jika tidak, aktifkan (Tahap 1).

Ketik:
```
python scripts/smoke_test_api.py
```
Yang muncul:
```text
[health] HTTP 200: {'status': 'ok', 'pipeline_mode': 'rules_only', ...}

[tanpa API key] HTTP 401 (seharusnya 401)
[deskripsi 5001 karakter] HTTP 422 (seharusnya 422)

[hard rule (harus reject, decided_by=rule)]
   alpr4 1mg buat tidur nyenyak
   -> reject | decided_by=rule | review_reason=None | pelanggaran=POL-DRG-01 ('alpra') | 0 ms
[produk biasa]
   Kaos polos cotton combed 30s
   -> approve | decided_by=rule | review_reason=None | pelanggaran=- | 0 ms
[klaim kesehatan (mode llm: dinilai LLM)]
   Kopi herbal, bisa sembuhkan diabetes
   -> needs_review | decided_by=rule | review_reason=rule_soft_hit | pelanggaran=- | 0 ms
[jebakan keyword (pistol air mainan)]
   Mainan pistol air untuk anak-anak
   -> approve | decided_by=rule | review_reason=None | pelanggaran=- | 0 ms

[kirim ulang request pertama] check_id sama dengan sebelumnya? YA, idempotensi bekerja
```

Untuk mengisi dashboard dengan lebih banyak contoh dari dev set, ketik juga:
```
python scripts/seed_demo.py
```

Kembali ke browser, **refresh** dashboard (tombol F5):
- Tab **Antrian review**: daftar listing di kiri, berkas listing di kanan. Kata yang cocok dengan rules diberi stabilo. Klik **Setujui listing** atau **Tolak listing** (menolak wajib memilih pasal). Listing pindah dari antrian.
- Tab **Riwayat**: semua keputusan, termasuk keputusan moderator.
- Tab **Statistik**: grafik keputusan dan alasan review.

Lihat juga Terminal 1: setiap request tercatat sebagai baris log.

---

## Tahap 6: Matikan API dan dashboard

Klik **Terminal 1**, tekan **Ctrl+C**. Yang muncul:
```text
API dan dashboard dimatikan.
```
Untuk menyalakan lagi kapan saja: `python scripts/run_local.py`.

---

## Tahap 7: Periksa dataset dan evaluasi tanpa AI

Ketik:
```
python scripts/validate_dataset.py data/eval/listings.jsonl data/policies/listing_policy.md
python scripts/split_dataset.py data/eval/listings.jsonl data/eval
python -m ai.evaluation.run_eval --split dev --mode rules_only
```
Yang muncul (potongan):
```text
OK: tidak ada masalah
dev : 101 listing, ...
test: 147 listing, ...
...
| violation_recall | 0.667 |
| reject_precision | 1.0 |
| automation_rate | 0.822 |
...
Laporan: reports/dev_rules_only_....md dan .json
```

Cek pengaman test set. Ketik:
```
python -m ai.evaluation.run_eval --split test --mode rules_only
```
Yang muncul (ini **benar**, perintahnya memang harus ditolak):
```text
Test set hanya untuk angka akhir. Tambahkan --final jika memang itu tujuannya.
```

---

## Tahap 8: Mode AI (butuh API key OpenAI)

### 8.1 Persiapan di website OpenAI
1. Buat API key di dashboard platform OpenAI. Pastikan akun punya saldo atau billing aktif.
2. Cek model yang tersedia untuk akun Anda. Konfigurasi default memakai `gpt-4o-mini`.
3. Buka halaman harga resmi OpenAI dan catat harga **input** dan **output** per 1 juta token untuk model itu.

### 8.2 Aktifkan mode AI
Ketik:
```
python scripts/make_env.py local --ai
```
Yang muncul:
```text
Tempel OPENAI_API_KEY (tidak akan terlihat saat diketik), lalu Enter:
```
Tempel API key Anda (Windows: klik kanan atau Ctrl+V; macOS: Cmd+V). **Tidak ada yang terlihat saat menempel. Ini normal.** Tekan Enter. Yang muncul:
```text
.env ditulis untuk mode 'local' (dengan AI).
  API key (untuk halaman /docs): dev-...
  OPENAI_API_KEY               : terisi (sk-pro...)
```
Jika model Anda bukan `gpt-4o-mini`: buka file `.env` di VS Code, ubah baris `LLM_MODEL=gpt-4o-mini` menjadi nama model Anda, simpan.

Untuk kembali ke mode tanpa AI: `python scripts/make_env.py local` (API key OpenAI tetap tersimpan).

### 8.3 Coba API dengan AI
Terminal 1:
```
python scripts/run_local.py
```
Terminal 2:
```
python scripts/smoke_test_api.py
```
Yang berbeda dari Tahap 5:
- `[health]` berisi `'pipeline_mode': 'llm'` dan `'policy_index': 'ok'`.
- "Kopi herbal" diputuskan dengan `decided_by=llm` atau `review_reason=rule_llm_disagree`; latency ratusan sampai ribuan ms.
- Pojok kanan atas dashboard: `Mode AI` dan nama model. Berkas listing menampilkan penilaian AI, meter keyakinan, dan stabilo pada kutipan yang dicurigai AI.

Jika `[health]` berisi `'status': 'degraded'` atau listing berakhir `review_reason=llm_unavailable`, cari nama error di log Terminal 1:

| Nama error di log | Artinya | Perbaikan |
|---|---|---|
| `AuthenticationError` | API key OpenAI salah | Jalankan ulang 8.2 setelah menghapus baris `OPENAI_API_KEY=...` di `.env` |
| `NotFoundError` | Nama model tidak tersedia | Ubah `LLM_MODEL` di `.env` |
| `BadRequestError` menyebut `temperature` | Model tidak menerima parameter temperature | Ubah baris di `.env` menjadi `LLM_TEMPERATURE=` (kosong) |
| `RateLimitError` | Terlalu banyak request atau saldo habis | Cek billing; pakai `--workers 1` saat evaluasi |

Matikan dengan Ctrl+C di Terminal 1 sebelum lanjut.

### 8.4 Evaluasi kecil dulu (5 listing)
Ketik:
```
python -m ai.evaluation.run_eval --split dev --mode llm_rag --limit 5 --workers 1
```
Pastikan tidak ada `llm_unavailable` di bagian "Alasan review".

### 8.5 Evaluasi penuh di dev set
Ketik:
```
python -m ai.evaluation.run_eval --split dev --mode llm_all
python -m ai.evaluation.run_eval --split dev --mode llm_rag
```
Untuk menghitung biaya, tambahkan harga dari 8.1. Contoh di bawah memakai 0.15 dan 0.60; **GANTI** kedua angka itu dengan harga input dan output model Anda:
```
python -m ai.evaluation.run_eval --split dev --mode llm_rag --price-in 0.15 --price-out 0.60
```
Jika banyak `llm_unavailable` karena rate limit, tambahkan `--workers 1` di akhir perintah.

### 8.6 Analisis dan pilih threshold
1. Buka file `.md` terbaru di folder `reports/` (di VS Code: klik kanan → Open Preview).
2. Untuk setiap ID di "Pelanggaran lolos" dan "Salah tolak", cari ID-nya di `data/eval/dev.jsonl` dan tulis penyebabnya: retrieval tidak mengambil pasal yang benar? jawaban LLM salah? label yang salah?
3. Lihat tabel "Simulasi threshold". Pilih nilai `t` yang memenuhi target recall dan precision dengan automation rate yang masih masuk akal.
4. Buka `.env` di VS Code, ubah `T_REJECT=` dan `T_APPROVE=` ke nilai pilihan Anda, simpan.
5. Catat alasan pilihan Anda sebagai ADR-018 di `docs/decision_log.md`.

---

## Tahap 9: Review label test set (wajib sebelum evaluasi final)

Tampilkan 20 listing per kali. Ketik:
```
python scripts/show_listings.py data/eval/test.jsonl --from 1 --to 20
```
Lanjutkan dengan `--from 21 --to 40`, `--from 41 --to 60`, dan seterusnya sampai 147.

Jika ada label yang salah, perbaiki langsung di `data/eval/listings.jsonl` (buka di VS Code, Ctrl+F cari ID-nya). Ikuti `docs/labeling_guideline.md`. **Jangan** mengedit `dev.jsonl` atau `test.jsonl`; keduanya dibuat ulang otomatis.

Setelah semua 147 dibaca, ketik:
```
python scripts/mark_reviewed.py data/eval/listings.jsonl data/eval/test.jsonl
python scripts/validate_dataset.py data/eval/listings.jsonl data/policies/listing_policy.md
python scripts/split_dataset.py data/eval/listings.jsonl data/eval
```
Yang muncul:
```text
147 listing ditandai reviewed. Jalankan validate_dataset.py lalu split_dataset.py.
...
OK: tidak ada masalah
dev : 101 listing, ...
test: 147 listing, ...
```

---

## Tahap 10: Evaluasi final (SEKALI saja)

**GANTI** 0.15 dan 0.60 dengan harga model Anda:
```
python -m ai.evaluation.run_eval --split test --mode llm_rag --final --price-in 0.15 --price-out 0.60
```
Masukkan angkanya ke tabel "Evaluasi" di `README.md`, apa pun hasilnya. Jangan mengubah prompt atau threshold lalu mengulang di test set.

---

## Tahap 11: Docker Compose

### 11.1 Install dan cek Docker
Install **Docker Desktop**, buka aplikasinya, tunggu sampai statusnya *running*. Ketik:
```
docker --version
docker compose version
```
Yang muncul: dua baris versi, tanpa error.

### 11.2 Ubah `.env` untuk Docker
Pastikan API lokal sudah dimatikan (Ctrl+C di Terminal 1). Ketik salah satu:

Dengan AI:
```
python scripts/make_env.py docker --ai
```
Tanpa AI:
```
python scripts/make_env.py docker
```
Di dalam Docker, database dan Redis diakses lewat nama service (`postgres`, `redis`), bukan `localhost`. Script ini mengatur itu.

### 11.3 Nyalakan semua service (Terminal 1)
```
docker compose up --build
```
Pertama kali butuh beberapa menit (download dan build). Tunggu sampai log berisi `"msg": "service siap"` dan `"msg": "worker siap"`.

### 11.4 Periksa (Terminal 2)
```
docker compose ps
```
Yang muncul: `api` berstatus `healthy`; `worker`, `dashboard`, `postgres`, `redis` berstatus `running` atau `Up`.

```
python scripts/smoke_test_api.py --batch
```
Yang muncul di akhir:
```text
[batch] HTTP 202 (seharusnya 202): {...'status': 'processing'...}
[batch] status akhir: {... 'status': 'completed', 'total': 4, 'pending': 0, 'done': 4, 'failed': 0, ...}
```
Buka http://localhost:8501 (dashboard) dan http://localhost:8000/health (harus berisi `"queue": "ok"`).

### 11.5 Matikan
Ctrl+C di Terminal 1, lalu:
```
docker compose down
```
Untuk kembali ke mode lokal tanpa Docker: `python scripts/make_env.py local --ai` (atau tanpa `--ai`).

### 11.6 Perintah lain
| Tujuan | Ketik |
|---|---|
| Lihat log API | `docker compose logs -f api` (Ctrl+C untuk berhenti melihat) |
| Lihat log worker | `docker compose logs worker` |
| Lihat log dashboard | `docker compose logs dashboard` |
| Jalankan 3 worker | `docker compose up -d --scale worker=3` |
| Matikan dan HAPUS data database | `docker compose down -v` |

---

## Tahap 12 (opsional): Latihan debugging

Jika belum pernah memakai git, set identitas Anda sekali (GANTI nama dan email; pakai email yang sama dengan akun GitHub Anda):
```
git config --global user.name "Nama Anda"
git config --global user.email "email-github-anda@contoh.com"
```
Lalu:
```
git init
git add .
git commit -m "baseline"
python exercises/break.py 1
python -m pytest -q
```
Petunjuk ada di `exercises/README.md`. Setelah selesai, kembalikan kode:
```
git checkout -- .
```

---

## Tahap 13: Sebelum upload ke GitHub

1. Jika repository untuk publik, hapus `STUDY_GUIDE.md` dan folder `exercises/` (keduanya catatan belajar pribadi).
2. Isi tabel hasil evaluasi di `README.md` dengan angka dari Tahap 8 dan 10.
3. Pastikan `.env` tidak ikut. Ketik:
```
git status
```
`.env` **tidak boleh** muncul di daftar (sudah diatur di `.gitignore`). Jika muncul, hentikan dan periksa `.gitignore`.
4. Cek siapa author commit. Ketik:
```
git log --format="%an <%ae>%n%b" -5
```
Yang muncul hanya nama dan email Anda. GitHub menentukan daftar *contributor* dari author commit dan baris `Co-authored-by:` di pesan commit.

---

## Masalah umum

| Gejala | Penyebab | Perbaikan |
|---|---|---|
| `No module named ...` | Virtual environment belum aktif | Aktifkan (Tahap 1), lalu ulangi |
| `File .env belum ada` | Tahap 3 dilewati | `python scripts/make_env.py local` |
| Dashboard: titik merah "API tidak terhubung" di kanan atas | API tidak berjalan | Jalankan `python scripts/run_local.py` (atau F5 di VS Code) |
| Dashboard: "API key ditolak" | `.env` dibuat ulang setelah API menyala | Matikan lalu jalankan lagi API dan dashboard |
| Dashboard tampil polos tanpa font khusus | Dashboard dijalankan dari folder yang salah | Jalankan lewat `run_local.py` atau VS Code, bukan `streamlit run dashboard/app.py` dari root |
| VS Code: `No module named uvicorn` saat F5 | Interpreter bukan `.venv` | Ctrl+Shift+P → `Python: Select Interpreter` → pilih yang berisi `.venv` |
| Browser: "This site can't be reached" di 8501 | Dashboard belum menyala atau sudah dimatikan | Lihat Terminal 1; jalankan `run_local.py` |
| `address already in use` / port 8000 atau 8501 dipakai | Ada API/dashboard/Docker lain yang masih menyala | Matikan terminal lain yang menjalankannya, atau `docker compose down` |
| Docker: `api` restart terus | Isi `.env` salah | `docker compose logs api`; jalankan ulang 11.2 |
| Docker: batch tidak selesai | Worker error | `docker compose logs worker` |

---

## Tahap 14: Deploy ke internet (Render, gratis)

Hasil akhir: dashboard bisa dibuka dari mana saja lewat alamat seperti `https://policyguard-xxxx.onrender.com`, dikunci dengan password Anda. Mode tanpa AI, jadi tidak ada biaya.

Yang perlu diketahui sebelum mulai:
- Server **tidur** setelah 15 menit tanpa pengunjung. Saat dibuka lagi, butuh sekitar 1 sampai 2 menit untuk bangun.
- Data **direset** setiap kali server bangun: listing contoh diisi ulang otomatis, dan keputusan moderator sebelumnya hilang. Ini batasan free tier (ADR-019).

### 14.1 Install Git (sekali saja)
Ketik di terminal:
```
git --version
```
Jika muncul `git version ...`, lanjut. Jika "not recognized" atau "command not found", install Git dari git-scm.com (Windows: klik Next sampai selesai), lalu tutup dan buka lagi VS Code.

Set identitas Anda (GANTI nama dan email; pakai email akun GitHub Anda):
```
git config --global user.name "Nama Anda"
git config --global user.email "email-github-anda@contoh.com"
```

### 14.2 Upload project ke GitHub lewat VS Code
1. Buat akun di github.com jika belum punya.
2. Di VS Code, klik ikon **Source Control** di bilah kiri (ikon cabang), atau tekan Ctrl+Shift+G.
3. Klik tombol **Publish to GitHub**.
4. Jika diminta, klik **Allow** lalu login GitHub di browser yang terbuka, kemudian kembali ke VS Code.
5. Pilih **Publish to GitHub private repository**. Private disarankan, karena ini masih latihan.
6. VS Code menampilkan daftar file yang akan diupload. Pastikan **`.env`, `.venv`, dan `policyguard.db` tidak ada di daftar** (sudah diatur `.gitignore`). Klik **OK**.
7. Tunggu notifikasi "Successfully published". Klik **Open on GitHub** untuk melihat repository Anda.

### 14.3 Deploy di Render
1. Buka render.com, klik **Get Started**, lalu daftar memakai akun **GitHub** (paling mudah).
2. Di dashboard Render, klik **New +**, lalu pilih **Blueprint**.
3. Hubungkan repository: jika repository Anda tidak muncul, klik **Configure account** / **Configure GitHub**, beri akses ke repository `policyguard`, lalu kembali.
4. Pilih repository `policyguard`, klik **Connect**.
5. Render membaca file `render.yaml` dan menampilkan service bernama **policyguard**. Isi **Blueprint Name** dengan nama apa saja.
6. Render meminta nilai **DASHBOARD_PASSWORD**. Isi dengan password pilihan Anda (minimal 12 karakter, jangan password yang dipakai di tempat lain). Simpan password ini.
7. Klik **Apply** / **Deploy Blueprint**.

Tampilan Render bisa sedikit berbeda dari tulisan di atas. Jika ada tombol yang tidak ditemukan, kirim screenshot-nya.

### 14.4 Tunggu sampai live
1. Klik service **policyguard**, lalu buka tab **Logs**.
2. Build pertama butuh sekitar 5 sampai 10 menit. Tunggu sampai log berisi:
```text
[start] API siap di 127.0.0.1:8000
[start] mengisi 40 listing contoh dari dev set
[start] dashboard berjalan di port 10000
```
dan status di atas berubah menjadi **Live**.
3. Klik alamat `https://policyguard-....onrender.com` di bagian atas halaman service.
4. Masukkan password dari 14.3 langkah 6, klik **Masuk**. Dashboard tampil.

### 14.5 Memperbarui setelah mengubah kode
1. Di VS Code, buka **Source Control**.
2. Tulis pesan singkat di kolom pesan (misalnya `perbaiki tampilan`), klik **Commit**, lalu klik **Sync Changes**.
3. Render otomatis build dan deploy ulang. Pantau di tab **Logs**.

### 14.6 Jika bermasalah
| Gejala | Penyebab dan solusi |
|---|---|
| Build gagal di tab Logs | Salin seluruh log error dan kirimkan |
| Status **Live** tapi halaman "Service Unavailable" atau lama sekali | Server sedang bangun dari tidur. Tunggu 1 sampai 2 menit lalu refresh |
| Log berisi `SERVICE_API_KEYS kosong` | Di Render: service → **Environment**, pastikan `SERVICE_API_KEYS` ada dan berisi |
| Lupa password dashboard | Di Render: service → **Environment** → ubah `DASHBOARD_PASSWORD` → **Save Changes**. Render deploy ulang |
| Render menolak karena kuota bulan habis | Free tier: 750 jam per bulan per workspace. Satu service yang tidur tidak menghabiskan jam |
