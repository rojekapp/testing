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
        # Jalur yang harus selalu bersih dari material.
        "access_paths": [
            {"name": "Jalur Evakuasi Utama", "polygon": [(350, 250), (620, 250), (620, 470), (350, 470)]},
        ],
    },
    {
        "id": "cam2",
        "name": "Pintu Masuk Proyek",
        "rtsp_url": os.getenv("CAM2_URL", "rtsp://admin:password@192.168.1.65:554/Streaming/Channels/102"),
        "zones": [],
        "access_paths": [
            {"name": "Pintu Darurat", "polygon": [(200, 200), (450, 200), (450, 460), (200, 460)]},
        ],
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

# ---------- Deteksi jalur terhalang material ----------
# Bekerja dengan membandingkan kondisi sekarang vs foto baseline jalur bersih.
# Ambil baseline dengan: python setup_path.py --baseline

OBSTRUCTION_DIFF_THRESHOLD = 35     # 0-255. Ambang perubahan TERANG. Kecil = sensitif
OBSTRUCTION_COLOR_THRESHOLD = 18    # 0-255. Ambang perubahan WARNA. Ini yang menangkap
                                    # material dengan kecerahan mirip permukaan jalur
OBSTRUCTION_TEXTURE_THRESHOLD = 0.06  # Ambang perubahan TEKSTUR permukaan. Dipakai untuk
                                    # membedakan material yang menimbun (tekstur hilang)
                                    # dari bayangan (tekstur tetap utuh).
                                    # Naikkan kalau bayangan masih sering terlapor.
OBSTRUCTION_MIN_BLOB_AREA = 1200    # piksel. Gumpalan lebih kecil dari ini diabaikan
OBSTRUCTION_MIN_AREA_RATIO = 0.12   # 12% luas jalur tertutup baru dianggap terhalang
OBSTRUCTION_CONFIRM_CHECKS = 3      # harus terdeteksi 3x berturut-turut baru dilaporkan
PERSON_BOX_PADDING = 15             # piksel. Area orang dilebarkan sedikit sebelum dikecualikan

# ---------- Penyimpanan di host ----------
DATA_DIR = os.getenv("SAFETY_DATA_DIR", "./data")
SNAPSHOT_DIR = os.path.join(DATA_DIR, "snapshots")
DB_PATH = os.path.join(DATA_DIR, "safety.db")
BASELINE_DIR = os.path.join(DATA_DIR, "baseline")

SAVE_ONLY_VIOLATIONS = True         # True = hemat disk, simpan gambar hanya saat ada pelanggaran
JPEG_QUALITY = 80
RETENTION_DAYS = 30                 # snapshot lebih tua dari ini dihapus otomatis

# ---------- Dashboard web lokal ----------
DASHBOARD_HOST = "0.0.0.0"          # 0.0.0.0 = bisa dibuka dari HP/laptop lain di LAN
DASHBOARD_PORT = 8080
