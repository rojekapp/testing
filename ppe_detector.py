"""
ppe_detector.py
Deteksi helm & rompi safety menggunakan pendekatan color thresholding (HSV).

Ini pendekatan klasik image processing (bukan deep learning) — cocok
sebagai starter project karena tidak butuh dataset/training/API key.
Cara kerja: crop area kepala & torso dari bounding box orang, lalu cek
seberapa besar porsi area itu match dengan warna khas helm/rompi safety.

CATATAN AKURASI:
Pendekatan warna ini cukup baik untuk demo/prototype, tapi bisa salah
kalau baju pekerja kebetulan warnanya mirip (misal kaos kuning).
Untuk produksi/akurasi tinggi, ganti fungsi check_ppe() dengan model
YOLO yang dilatih khusus deteksi APD (lihat README.md bagian "Upgrade").
"""

import cv2
import numpy as np

from config import HELMET_HSV_RANGES, VEST_HSV_RANGES, HELMET_MIN_RATIO, VEST_MIN_RATIO


def _color_ratio(region, hsv_ranges):
    """Hitung rasio piksel yang match salah satu range warna, terhadap total area region."""
    if region.size == 0:
        return 0.0
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    total_mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lower, upper in hsv_ranges:
        mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
        total_mask = cv2.bitwise_or(total_mask, mask)
    return np.count_nonzero(total_mask) / total_mask.size


def check_ppe(person_crop):
    """
    person_crop: gambar hasil crop bounding box orang (format BGR, dari OpenCV).
    Return: dict -> {"helmet": bool, "vest": bool}
    """
    h, w = person_crop.shape[:2]
    if h == 0 or w == 0:
        return {"helmet": False, "vest": False}

    # Area kepala: 0% - 25% tinggi dari atas bounding box
    head_region = person_crop[0:int(h * 0.25), :]
    # Area torso/badan: 25% - 65% tinggi
    torso_region = person_crop[int(h * 0.25):int(h * 0.65), :]

    helmet_ratio = _color_ratio(head_region, HELMET_HSV_RANGES)
    vest_ratio = _color_ratio(torso_region, VEST_HSV_RANGES)

    return {
        "helmet": helmet_ratio >= HELMET_MIN_RATIO,
        "vest": vest_ratio >= VEST_MIN_RATIO,
    }
