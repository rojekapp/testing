# Safety Monitor CCTV — Deteksi APD & Zona Terlarang

Versi untuk dipasang di lokasi proyek: PC/mini PC terhubung ke CCTV lewat
jaringan lokal, mengambil gambar berkala, menganalisis, dan menyimpan
semua hasilnya di mesin itu sendiri.

- Deteksi APD (helm & rompi) dan orang masuk zona terlarang
- Capture berkala dari beberapa kamera sekaligus lewat RTSP
- Semua data disimpan lokal: SQLite + snapshot JPEG
- Dashboard web yang bisa dibuka dari HP/laptop di jaringan yang sama
- Jalan sebagai service, otomatis nyala lagi kalau mati atau PC restart
- Pembersihan data lama otomatis sesuai batas retensi

Tidak ada data yang keluar dari jaringan lokal.

---

## 1. Kebutuhan hardware

Karena deteksi berjalan berkala (bukan real-time terus-menerus), kebutuhannya ringan:

| Komponen | Minimum | Disarankan |
|---|---|---|
| CPU | 4 core (Intel N100, i3, Ryzen 3) | Intel N100 / i5 |
| RAM | 4 GB | 8 GB |
| Penyimpanan | 128 GB SSD | 256 GB SSD |
| OS | Ubuntu Server 22.04 / Debian 12 | sama |
| GPU | tidak perlu | — |

Mini PC kelas Intel N100 sudah lebih dari cukup untuk 2–6 kamera pada
interval beberapa menit. Satu kali pengecekan per kamera memakan sekitar
1–3 detik CPU.

Pastikan mini PC dan semua CCTV berada di jaringan/VLAN yang sama, dan
sebaiknya diberi IP statis lewat DHCP reservation di router.

---

## 2. Instalasi

```bash
# di mini PC lokasi
sudo apt update && sudo apt install -y python3-venv python3-pip ffmpeg

sudo mkdir -p /opt/safety-monitor
sudo chown $USER:$USER /opt/safety-monitor
cd /opt/safety-monitor

# salin semua file project ke sini, lalu:
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

Saat pertama kali dijalankan, model deteksi orang (YOLOv8n, ~6 MB) otomatis
diunduh. Butuh internet **sekali saja** — setelah itu sistem bisa jalan
sepenuhnya offline. Kalau mini PC tidak punya internet sama sekali, unduh
`yolov8n.pt` di komputer lain lalu salin ke folder project.

---

## 3. Konfigurasi kamera

Edit `CAMERAS` di `config.py`. Yang penting:

**Pakai sub-stream, bukan main stream.** Sub-stream biasanya 640x480 dan
jauh lebih ringan. Deteksi tidak butuh resolusi 4K.

Format URL RTSP per merk (cek manual kamera kamu untuk memastikan):

| Merk | Contoh URL sub-stream |
|---|---|
| Hikvision | `rtsp://user:pass@IP:554/Streaming/Channels/102` |
| Dahua | `rtsp://user:pass@IP:554/cam/realmonitor?channel=1&subtype=1` |
| Uniview | `rtsp://user:pass@IP:554/media/video2` |
| Generic ONVIF | `rtsp://user:pass@IP:554/stream2` |

Password sebaiknya tidak ditulis langsung di `config.py`, melainkan lewat
environment variable (lihat file service di langkah 5).

Setelah diisi, tes koneksinya:

```bash
./venv/bin/python monitor.py --test-cameras
```

Kalau gagal, cek: IP kamera benar, RTSP aktif di setting kamera, user/password
benar, dan mini PC bisa `ping` ke IP kamera.

---

## 4. Menentukan zona terlarang

Koordinat zona bergantung sudut pandang tiap kamera, jadi harus diatur sekali
per kamera setelah CCTV terpasang di posisi finalnya.

```bash
# di mini PC (tanpa perlu layar) - ambil gambar referensi tiap kamera
./venv/bin/python setup_zone.py --grab
```

Salin folder `data/reference/` ke laptop yang ada layarnya, lalu:

```bash
python setup_zone.py --draw cam1.jpg
```

Klik titik-titik sudut zona, tekan `s`, lalu salin koordinat yang tercetak
ke bagian `zones` kamera terkait di `config.py`.

Kamera yang tidak perlu pengawasan zona cukup diberi `"zones": []` — kamera
itu tetap mengecek APD.

---

## 5. Menjalankan sebagai service

Supaya jalan otomatis dan nyala lagi setelah mati listrik:

```bash
# buat user khusus (opsional tapi disarankan)
sudo useradd -r -s /bin/false safety
sudo chown -R safety:safety /opt/safety-monitor

# edit dulu password kamera di dalam file service
sudo nano safety-monitor.service

sudo cp safety-monitor.service safety-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now safety-monitor safety-dashboard
```

Cek status dan log:

```bash
systemctl status safety-monitor
journalctl -u safety-monitor -f
```

---

## 6. Membuka dashboard

Dari HP atau laptop yang terhubung ke jaringan/WiFi yang sama:

```
http://<ip-mini-pc>:8080
```

Cari IP mini PC dengan `hostname -I`. Dashboard menampilkan foto bukti,
waktu, kamera, dan jenis pelanggaran, dengan filter per kamera.

Dashboard ini tidak punya login, jadi jangan diekspos ke internet. Kalau
perlu akses dari luar lokasi, pakai VPN (mis. WireGuard/Tailscale) ke
jaringan proyek — jangan port forwarding.

---

## 7. Pengaturan yang sering disesuaikan

Semua di `config.py`:

| Setting | Fungsi |
|---|---|
| `CAPTURE_INTERVAL_SECONDS` | Jarak antar pengecekan (default 180 detik) |
| `FRAMES_PER_CHECK` | Frame per pengecekan; lebih banyak = lebih teliti, lebih berat |
| `ACTIVE_HOURS_START` / `END` | Jam kerja; di luar itu capture dilewati |
| `SAVE_ONLY_VIOLATIONS` | `True` = simpan foto hanya saat ada pelanggaran (hemat disk) |
| `RETENTION_DAYS` | Umur maksimal data sebelum dihapus otomatis |
| `HELMET_MIN_RATIO` / `VEST_MIN_RATIO` | Sensitivitas deteksi APD |

**Perkiraan pemakaian disk:** dengan 2 kamera, interval 3 menit, jam kerja
12 jam, dan hanya menyimpan pelanggaran, pemakaian umumnya di bawah 1 GB per
bulan. Kalau `SAVE_ONLY_VIOLATIONS = False`, bisa naik ke sekitar 10–15 GB
per bulan.

---

## 8. Struktur project

```
safety-monitor/
├── monitor.py            # service utama (loop capture berkala)
├── dashboard.py           # web dashboard lokal
├── setup_zone.py          # tool atur zona terlarang
├── capture.py             # ambil frame dari RTSP
├── analyzer.py            # gabung deteksi orang + APD + zona
├── detector.py            # deteksi orang (YOLOv8)
├── ppe_detector.py        # deteksi helm & rompi (warna HSV)
├── zone.py                # logika zona terlarang
├── storage.py             # SQLite + snapshot + retensi
├── config.py              # semua pengaturan
├── requirements.txt
├── safety-monitor.service
├── safety-dashboard.service
└── data/                  # dibuat otomatis
    ├── safety.db
    ├── snapshots/YYYY-MM-DD/
    └── reference/
```

---

## 9. Batasan yang perlu diketahui

**Deteksi APD pakai analisis warna (HSV), bukan model khusus APD.** Ini
ringan dan tidak butuh training, tapi akurasinya terbatas:

- Baju pekerja berwarna mirip helm/rompi bisa terbaca sebagai APD (false negative pelanggaran)
- Pencahayaan sore/mendung/backlight menurunkan akurasi cukup signifikan
- Pekerja yang membelakangi kamera atau tertutup material bisa salah baca
- Jarak jauh membuat area kepala terlalu kecil untuk dinilai warnanya

Karena itu, **sistem ini sebaiknya diposisikan sebagai alat bantu pengawasan,
bukan dasar penindakan otomatis.** Selalu ada foto bukti di dashboard supaya
petugas K3 bisa memverifikasi sendiri sebelum menindaklanjuti.

**Untuk akurasi tingkat produksi**, ganti fungsi `check_ppe()` di
`ppe_detector.py` dengan model YOLO yang dilatih khusus APD:

1. Ambil dataset "PPE detection" / "hard hat detection" dari Roboflow Universe,
   atau kumpulkan dan labeli foto dari lokasi sendiri (lebih akurat karena
   sesuai kondisi pencahayaan dan seragam di lapangan)
2. Latih: `yolo train data=ppe.yaml model=yolov8n.pt epochs=50`
3. Ubah `analyzer.py` agar membaca kelas hasil model (`helmet`, `no-helmet`,
   `vest`, `no-vest`) langsung, bukan lewat analisis warna

Struktur project sengaja dipisah per modul supaya penggantian ini tidak
mengubah `monitor.py`, `storage.py`, atau `dashboard.py` sama sekali.

---

## 10. Catatan privasi & kepatuhan

Sistem ini merekam gambar pekerja. Sebelum dioperasikan:

- Beri tahu pekerja dan pasang papan pemberitahuan area terpantau CCTV
- Batasi akses dashboard hanya ke petugas yang berkepentingan
- Simpan data sesingkat yang dibutuhkan (`RETENTION_DAYS`)
- Sesuaikan dengan kebijakan perusahaan dan ketentuan perlindungan data
  pribadi yang berlaku
