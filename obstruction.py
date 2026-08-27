"""
obstruction.py
Deteksi jalur akses / pintu darurat yang terhalang material.

CARA KERJANYA (tanpa perlu training model):
Sistem menyimpan foto "baseline" tiap jalur dalam kondisi bersih. Setiap
pengecekan, frame saat ini dibandingkan dengan baseline. Area di dalam
polygon jalur yang berubah signifikan dianggap sebagai objek asing —
yaitu material yang menghalangi.

Pendekatan ini sengaja tidak peduli JENIS materialnya. Untuk tujuan
keselamatan, yang penting adalah "jalur ini terhalang", bukan "yang
menghalangi itu semen atau besi".

TIGA PENYARING supaya tidak asal lapor:
1. Area orang dikecualikan. Pekerja yang lewat bukan halangan.
2. Bercak kecil diabaikan. Hanya gumpalan di atas ukuran minimum
   yang dihitung, jadi daun jatuh atau noise kamera tidak terhitung.
3. Harus bertahan beberapa kali pengecekan berturut-turut sebelum
   dilaporkan. Truk yang berhenti sebentar lalu pergi tidak dilaporkan,
   tumpukan material yang menetap dilaporkan.

BATASAN yang perlu disadari:
Perubahan cahaya besar (matahari muncul dari balik awan, lampu menyala,
bayangan panjang sore hari) bisa memicu laporan palsu. Karena itu
baseline sebaiknya diambil ulang saat kondisi pencahayaan lokasi
berubah signifikan, atau ambil beberapa baseline untuk waktu berbeda.
"""

import os

import cv2
import numpy as np

from config import (
    BASELINE_DIR, OBSTRUCTION_DIFF_THRESHOLD, OBSTRUCTION_COLOR_THRESHOLD,
    OBSTRUCTION_TEXTURE_THRESHOLD, OBSTRUCTION_MIN_BLOB_AREA,
    OBSTRUCTION_MIN_AREA_RATIO, PERSON_BOX_PADDING,
)


def baseline_path(camera_id, path_name):
    """Lokasi file baseline untuk satu jalur pada satu kamera."""
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in path_name)
    return os.path.join(BASELINE_DIR, f"{camera_id}__{safe_name}.jpg")


def save_baseline(frame, camera_id, path_name):
    os.makedirs(BASELINE_DIR, exist_ok=True)
    path = baseline_path(camera_id, path_name)
    cv2.imwrite(path, frame)
    return path


def load_baseline(camera_id, path_name):
    """Return gambar baseline, atau None kalau belum pernah diambil."""
    path = baseline_path(camera_id, path_name)
    if not os.path.exists(path):
        return None
    return cv2.imread(path)


def _prepare(img):
    """
    Pecah gambar jadi tiga kanal LAB: terang (L) dan warna (a, b).

    Kenapa LAB, bukan grayscale:
    perbandingan grayscale saja akan melewatkan material yang kecerahannya
    mirip permukaan jalan — misalnya tumpukan pasir di atas aspal. Padahal
    warnanya jelas berbeda. Kanal a dan b menangkap perbedaan warna itu.

    Bonusnya, pemisahan ini juga menekan laporan palsu akibat bayangan dan
    perubahan cahaya, karena keduanya terutama mengubah L, bukan a dan b.

    CLAHE diterapkan pada L supaya perbedaan pencahayaan menyeluruh antara
    baseline dan frame sekarang tidak langsung terbaca sebagai objek baru.
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    L, a, b = cv2.split(lab)

    texture = _texture_map(L)  # dihitung dari L asli, sebelum CLAHE

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    L = clahe.apply(L)

    blur = lambda c: cv2.GaussianBlur(c, (7, 7), 0)
    return blur(L), blur(a), blur(b), texture


def _texture_map(L):
    """
    Peta tekstur permukaan yang tidak terpengaruh terang-gelapnya cahaya.

    Kuncinya ada di pembagian dengan rata-rata terang setempat. Kalau area
    tertutup bayangan, kekuatan tepi DAN rata-rata terangnya turun dengan
    faktor yang sama, sehingga hasil baginya tetap. Kalau area tertutup
    material, pola permukaannya benar-benar berganti dan hasil baginya ikut
    berubah.

    Inilah yang membedakan "aspal yang kena bayangan" dari "aspal yang
    tertimbun material" — keduanya sama-sama menggelap, tapi hanya yang
    kedua kehilangan tekstur aslinya.
    """
    Lf = L.astype(np.float32)
    gx = cv2.Sobel(Lf, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(Lf, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(gx, gy)

    local_brightness = cv2.GaussianBlur(Lf, (31, 31), 0) + 1.0
    normalized = magnitude / local_brightness

    return cv2.GaussianBlur(normalized, (9, 9), 0)


def _zone_mask(shape, polygon):
    mask = np.zeros(shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [np.array(polygon, dtype=np.int32)], 255)
    return mask


def check_path(frame, baseline, polygon, person_boxes=None):
    """
    Bandingkan frame dengan baseline di dalam area polygon jalur.

    Return dict:
        blocked_ratio : porsi luas jalur yang terhalang (0.0 - 1.0)
        is_blocked    : True kalau melewati ambang batas
        mask          : mask area terhalang, untuk digambar di snapshot
    """
    if baseline is None:
        return {"blocked_ratio": 0.0, "is_blocked": False, "mask": None,
                "error": "baseline belum diambil"}

    # Ukuran baseline dan frame harus sama supaya bisa dibandingkan
    if baseline.shape[:2] != frame.shape[:2]:
        baseline = cv2.resize(baseline, (frame.shape[1], frame.shape[0]))

    zone = _zone_mask(frame.shape, polygon)
    zone_area = int(np.count_nonzero(zone))
    if zone_area == 0:
        return {"blocked_ratio": 0.0, "is_blocked": False, "mask": None,
                "error": "polygon jalur tidak valid"}

    L1, a1, b1, tex1 = _prepare(baseline)
    L2, a2, b2, tex2 = _prepare(frame)

    # Bukti 1 - perubahan WARNA. Bukti terkuat, karena bayangan hampir tidak
    # mengubah warna permukaan. Ini sendirian sudah cukup.
    diff_color = cv2.add(cv2.absdiff(a1, a2), cv2.absdiff(b1, b2))
    _, mask_color = cv2.threshold(diff_color, OBSTRUCTION_COLOR_THRESHOLD, 255, cv2.THRESH_BINARY)

    # Bukti 2 - perubahan TERANG. Tidak bisa berdiri sendiri: bayangan awan
    # dan bayangan sore juga menggelapkan area tanpa ada material apa pun.
    diff_light = cv2.absdiff(L1, L2)
    _, mask_light = cv2.threshold(diff_light, OBSTRUCTION_DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)

    # Bukti 3 - perubahan TEKSTUR. Inilah penengahnya. Material menutupi dan
    # mengganti pola permukaan; bayangan membiarkannya utuh.
    diff_texture = cv2.absdiff(tex1, tex2)
    mask_texture = (diff_texture > OBSTRUCTION_TEXTURE_THRESHOLD).astype(np.uint8) * 255

    # Objek asing = warna berubah, ATAU (menggelap/menerang DAN tekstur hilang).
    # Area yang cuma menggelap tapi teksturnya utuh dianggap bayangan, diabaikan.
    binary = cv2.bitwise_or(mask_color, cv2.bitwise_and(mask_light, mask_texture))

    # Rapikan: buang bintik halus, lalu sambungkan area yang terpecah
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=3)

    # Batasi hanya di dalam jalur
    binary = cv2.bitwise_and(binary, zone)

    # Penyaring 1: orang yang lewat bukan halangan
    for box in (person_boxes or []):
        x1, y1, x2, y2 = box
        pad = PERSON_BOX_PADDING
        x1 = max(0, x1 - pad)
        y1 = max(0, y1 - pad)
        x2 = min(frame.shape[1], x2 + pad)
        y2 = min(frame.shape[0], y2 + pad)
        binary[y1:y2, x1:x2] = 0

    # Penyaring 2: hanya gumpalan cukup besar yang dihitung
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    clean = np.zeros_like(binary)
    for i in range(1, n_labels):  # label 0 = background
        if stats[i, cv2.CC_STAT_AREA] >= OBSTRUCTION_MIN_BLOB_AREA:
            clean[labels == i] = 255

    blocked_area = int(np.count_nonzero(clean))
    ratio = blocked_area / zone_area

    return {
        "blocked_ratio": round(ratio, 3),
        "is_blocked": ratio >= OBSTRUCTION_MIN_AREA_RATIO,
        "mask": clean if blocked_area else None,
        "error": None,
    }


def draw_paths(frame, paths, results=None):
    """
    Gambar jalur akses di frame.
    Biru = jalur bersih, oranye tebal + arsiran = terhalang.
    """
    results = results or {}
    overlay = frame.copy()

    for p in paths:
        poly = np.array(p["polygon"], dtype=np.int32)
        res = results.get(p["name"], {})
        blocked = res.get("confirmed_blocked", False)

        color = (0, 140, 255) if blocked else (255, 160, 0)  # BGR

        if blocked and res.get("mask") is not None:
            overlay[res["mask"] > 0] = color

        cv2.polylines(frame, [poly], isClosed=True, color=color,
                      thickness=3 if blocked else 2)

        label = p["name"]
        if blocked:
            label += f" TERHALANG {int(res.get('blocked_ratio', 0) * 100)}%"
        cv2.putText(frame, label, tuple(poly[0]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, frame)
    return frame
