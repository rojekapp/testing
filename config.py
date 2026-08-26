"""
config.py
Pengaturan Safety Monitor versi CCTV (dijalankan di PC/mini PC lokasi).

Yang paling sering diubah: CAMERAS dan CAPTURE_INTERVAL_SECONDS.
"""

import os

# ---------- Kamera CCTV ----------
# Isi url RTSP tiap kamera. Format umum (cek manual merk kamera kamu):
#   Hikvision : rtsp://user:pass@192.168.1.64:554/Streaming/Channels/102
#   Dahua     : rtsp://user:pass@192.168.1.108:554/cam/realmonitor?channel=1&subtype=1
#   Generic   : rtsp://user:pass@192.168.1.10:554/stream2
#
# Tips: pakai SUB-STREAM (biasanya 640x480 / 704x576), bukan main stream 4K.
# Deteksi tidak butuh resolusi tinggi, dan sub-stream jauh lebih ringan.
#
# Zona terlarang didefinisikan PER KAMERA, karena sudut pandang tiap kamera beda.
# Kosongkan list polygon kalau kamera itu cuma untuk cek APD.
CAMERAS = [
    {
        "id": "cam1",
        "name": "Area Alat Berat",
        "rtsp_url": os.getenv("CAM1_URL", "rtsp://admin:password@192.168.1.64:554/Streaming/Channels/102"),
        "zones": [
            {"name": "Radius Excavator", "polygon": [(50, 300), (300, 300), (300, 470), (50, 470)]},
        ],
    },
    {
        "id": "cam2",
        "name": "Pintu Masuk Proyek",
        "rtsp_url": os.getenv("CAM2_URL", "rtsp://admin:password@192.168.1.65:554/Streaming/Channels/102"),
        "zones": [],
    },
]

# ---------- Jadwal capture ----------
CAPTURE_INTERVAL_SECONDS = 180      # cek tiap 3 menit
FRAMES_PER_CHECK = 3                # ambil 3 frame per pengecekan, pilih hasil terburuk
FRAME_GAP_SECONDS = 2               # jeda antar frame dalam satu pengecekan

# Jam operasional (24 jam). Di luar jam ini, capture dilewati.
# Malam hari biasanya gelap & tidak ada pekerja, jadi hemat resource.
ACTIVE_HOURS_START = 6              # 06:00
ACTIVE_HOURS_END = 18               # 18:00
# Set ACTIVE_HOURS_START = 0 dan ACTIVE_HOURS_END = 24 untuk jalan 24 jam.

# ---------- Model deteksi orang ----------
MODEL_PATH = "yolov8n.pt"
CONF_THRESHOLD = 0.4

# ---------- Deteksi APD (warna HSV) ----------
HELMET_HSV_RANGES = [
    ((20, 100, 100), (35, 255, 255)),    # kuning
    ((0, 0, 200), (180, 40, 255)),       # putih
    ((0, 100, 100), (10, 255, 255)),     # merah (hue bawah)
    ((160, 100, 100), (180, 255, 255)),  # merah (hue atas)
    ((90, 80, 80), (130, 255, 255)),     # biru
]
VEST_HSV_RANGES = [
    ((10, 150, 150), (25, 255, 255)),    # oranye neon
    ((35, 100, 100), (85, 255, 255)),    # hijau-kuning neon
]
HELMET_MIN_RATIO = 0.15
VEST_MIN_RATIO = 0.12

# ---------- Penyimpanan di host ----------
DATA_DIR = os.getenv("SAFETY_DATA_DIR", "./data")
SNAPSHOT_DIR = os.path.join(DATA_DIR, "snapshots")
DB_PATH = os.path.join(DATA_DIR, "safety.db")

SAVE_ONLY_VIOLATIONS = True         # True = hemat disk, simpan gambar hanya saat ada pelanggaran
JPEG_QUALITY = 80
RETENTION_DAYS = 30                 # snapshot lebih tua dari ini dihapus otomatis

# ---------- Dashboard web lokal ----------
DASHBOARD_HOST = "0.0.0.0"          # 0.0.0.0 = bisa dibuka dari HP/laptop lain di LAN
DASHBOARD_PORT = 8080
