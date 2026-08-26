"""
zone.py
Modul untuk mengecek apakah seseorang masuk ke zona terlarang/berbahaya,
dan untuk menggambar zona tersebut di atas frame.
"""

import cv2
import numpy as np


def is_point_in_zone(point, polygon):
    """point: (x, y). polygon: list titik (x, y). Return True jika point ada di dalam polygon."""
    poly_np = np.array(polygon, dtype=np.int32)
    result = cv2.pointPolygonTest(poly_np, point, False)
    return result >= 0


def get_foot_point(bbox):
    """Ambil titik 'kaki' (bottom-center) dari bounding box — representasi posisi orang berdiri."""
    x1, y1, x2, y2 = bbox
    return (int((x1 + x2) / 2), int(y2))


def draw_zones(frame, zones):
    """Gambar semua zona terlarang di frame (isi merah transparan + garis tepi + label)."""
    overlay = frame.copy()
    for zone in zones:
        poly_np = np.array(zone["polygon"], dtype=np.int32)
        cv2.fillPoly(overlay, [poly_np], (0, 0, 255))
        cv2.polylines(frame, [poly_np], isClosed=True, color=(0, 0, 255), thickness=2)
        label_pos = tuple(poly_np[0])
        cv2.putText(frame, zone["name"], label_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
    return frame
