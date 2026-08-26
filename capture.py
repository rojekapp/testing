"""
capture.py
Ambil frame dari kamera CCTV lewat RTSP.

Kenapa tidak buka stream terus-menerus:
karena mode kerjanya berkala (tiap beberapa menit), koneksi dibuka
saat butuh lalu langsung ditutup. Ini jauh lebih hemat CPU/RAM dan
tidak bermasalah kalau jaringan sempat putus.

Catatan penting soal RTSP:
OpenCV menyimpan frame di buffer internal. Frame pertama yang terbaca
sering merupakan frame lama (basi). Karena itu beberapa frame awal
sengaja dibuang sebelum frame yang dipakai diambil.
"""

import os
import time

import cv2

# Pakai TCP untuk RTSP — lebih stabil daripada UDP di jaringan proyek
# yang sering ramai. Harus diset sebelum VideoCapture dibuat.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

WARMUP_FRAMES = 5          # jumlah frame basi yang dibuang
OPEN_TIMEOUT_SECONDS = 15


def grab_frame(rtsp_url, retries=2):
    """
    Ambil satu frame terbaru dari kamera.

    Return: frame (numpy array BGR), atau None kalau gagal.
    """
    for attempt in range(retries + 1):
        cap = None
        try:
            cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            start = time.time()
            while not cap.isOpened() and time.time() - start < OPEN_TIMEOUT_SECONDS:
                time.sleep(0.5)

            if not cap.isOpened():
                raise ConnectionError("tidak bisa membuka stream")

            # Buang frame basi dari buffer
            for _ in range(WARMUP_FRAMES):
                cap.read()

            ret, frame = cap.read()
            if not ret or frame is None:
                raise ConnectionError("stream terbuka tapi frame kosong")

            return frame

        except Exception as e:
            if attempt < retries:
                time.sleep(2)
                continue
            print(f"[capture] Gagal ambil frame dari kamera: {e}")
            return None

        finally:
            if cap is not None:
                cap.release()


def grab_frames(rtsp_url, count=3, gap_seconds=2):
    """
    Ambil beberapa frame berjarak beberapa detik dalam satu sesi pengecekan.
    Berguna supaya orang yang kebetulan tertutup objek di satu frame
    masih tertangkap di frame berikutnya.
    """
    frames = []
    for i in range(count):
        frame = grab_frame(rtsp_url)
        if frame is not None:
            frames.append(frame)
        if i < count - 1:
            time.sleep(gap_seconds)
    return frames


def test_camera(rtsp_url):
    """Cek cepat apakah satu kamera bisa diakses. Return (berhasil, pesan)."""
    frame = grab_frame(rtsp_url, retries=1)
    if frame is None:
        return False, "Gagal terhubung"
    h, w = frame.shape[:2]
    return True, f"OK - resolusi {w}x{h}"
