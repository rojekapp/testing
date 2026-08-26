"""
analyzer.py
Menggabungkan tiga modul deteksi (orang, APD, zona) jadi satu hasil
per frame, lengkap dengan gambar yang sudah dianotasi.
"""

import cv2

from detector import PersonDetector
from ppe_detector import check_ppe
from zone import draw_zones, get_foot_point, is_point_in_zone
from config import MODEL_PATH, CONF_THRESHOLD

_detector = None


def get_detector():
    """Model dimuat sekali saja lalu dipakai ulang (loading model itu mahal)."""
    global _detector
    if _detector is None:
        _detector = PersonDetector(MODEL_PATH, CONF_THRESHOLD)
    return _detector


def analyze(frame, zones):
    """
    frame: gambar BGR dari kamera.
    zones: list zona terlarang untuk kamera ini (bisa list kosong).

    Return: (frame_beranotasi, hasil_dict)
    """
    detector = get_detector()
    detections = detector.detect(frame)

    annotated = frame.copy()
    if zones:
        annotated = draw_zones(annotated, zones)

    no_helmet = 0
    no_vest = 0
    in_zone = 0
    labels = []

    for i, det in enumerate(detections):
        x1, y1, x2, y2 = det["bbox"]
        ppe = check_ppe(frame[y1:y2, x1:x2])

        foot = get_foot_point(det["bbox"])
        person_in_zone = any(is_point_in_zone(foot, z["polygon"]) for z in zones)

        pelanggaran = []
        if not ppe["helmet"]:
            pelanggaran.append("Tanpa Helm")
            no_helmet += 1
        if not ppe["vest"]:
            pelanggaran.append("Tanpa Rompi")
            no_vest += 1
        if person_in_zone:
            pelanggaran.append("Masuk Zona Terlarang")
            in_zone += 1

        color = (0, 0, 255) if pelanggaran else (0, 200, 0)
        text = f"#{i + 1}: " + (", ".join(pelanggaran) if pelanggaran else "AMAN")

        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        cv2.putText(annotated, text, (x1, max(y1 - 8, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        cv2.circle(annotated, foot, 4, color, -1)

        if pelanggaran:
            labels.append(text)

    result = {
        "person_count": len(detections),
        "no_helmet": no_helmet,
        "no_vest": no_vest,
        "in_zone": in_zone,
        "is_violation": bool(labels),
        "detail": "; ".join(labels) if labels else "Semua aman",
    }

    return annotated, result


def score(result):
    """Skor keparahan, dipakai untuk memilih frame terburuk dari beberapa frame."""
    return result["no_helmet"] + result["no_vest"] + result["in_zone"] * 2
