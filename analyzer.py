"""
analyzer.py
Menggabungkan seluruh pemeriksaan untuk satu frame:
  1. Deteksi orang (YOLOv8)
  2. APD: helm & rompi (analisis warna)
  3. Zona terlarang: orang masuk area berbahaya
  4. Jalur akses: material menghalangi jalur evakuasi / pintu darurat

Alur yang dipakai service adalah analyze_frames(): beberapa frame dinilai,
yang terburuk dipilih, lalu status jalur baru diperbarui SATU KALI.
Pemisahan ini penting — kalau tiap frame ikut menaikkan hitungan, syarat
"harus bertahan beberapa kali pengecekan" akan terpenuhi hanya dalam satu
siklus, dan penyaring alarm palsu jadi tidak ada gunanya.
"""

import cv2

from config import MODEL_PATH, CONF_THRESHOLD, OBSTRUCTION_CONFIRM_CHECKS
from detector import PersonDetector
from obstruction import check_path, draw_paths, load_baseline
from ppe_detector import check_ppe
from storage import bump_path_state
from zone import draw_zones, get_foot_point, is_point_in_zone

_detector = None


def get_detector():
    """Model dimuat sekali saja lalu dipakai ulang (loading model itu mahal)."""
    global _detector
    if _detector is None:
        _detector = PersonDetector(MODEL_PATH, CONF_THRESHOLD)
    return _detector


# --------------------------------------------------------------------------
# Penilaian (tidak menggambar apa pun)
# --------------------------------------------------------------------------

def _evaluate(frame, camera):
    """
    Nilai satu frame tanpa menyentuh status jalur di database.

    Return: (result, detections)
    """
    detector = get_detector()
    detections = detector.detect(frame)
    person_boxes = [d["bbox"] for d in detections]

    zones = camera.get("zones", [])

    # Jalur diperiksa memakai frame asli, sebelum digambari apa pun
    path_results = {}
    for p in camera.get("access_paths", []):
        baseline = load_baseline(camera["id"], p["name"])
        res = check_path(frame, baseline, p["polygon"], person_boxes)
        res.setdefault("consecutive", 0)
        res["confirmed_blocked"] = False  # ditentukan nanti saat commit
        path_results[p["name"]] = res

    no_helmet = 0
    no_vest = 0
    in_zone = 0
    labels = []
    per_person = []

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

        text = f"#{i + 1}: " + (", ".join(pelanggaran) if pelanggaran else "AMAN")
        per_person.append({"bbox": det["bbox"], "foot": foot,
                           "text": text, "violation": bool(pelanggaran)})
        if pelanggaran:
            labels.append(text)

    result = {
        "person_count": len(detections),
        "no_helmet": no_helmet,
        "no_vest": no_vest,
        "in_zone": in_zone,
        "blocked_paths": 0,
        "block_detail": "",
        "missing_baseline": [n for n, r in path_results.items() if r.get("error")],
        "person_labels": labels,
        "per_person": per_person,
        "path_results": path_results,
        "is_violation": bool(labels),
        "detail": "; ".join(labels) if labels else "Semua aman",
    }
    return result, detections


def _commit_path_state(camera, result):
    """
    Perbarui status jalur di database, tepat sekali per siklus pengecekan,
    lalu tentukan jalur mana yang sudah cukup lama terhalang untuk dilaporkan.
    """
    for name, res in result["path_results"].items():
        if res.get("error"):
            continue
        consecutive, first_seen = bump_path_state(
            camera["id"], name, res["is_blocked"], res["blocked_ratio"]
        )
        res["consecutive"] = consecutive
        res["first_seen"] = first_seen
        res["confirmed_blocked"] = consecutive >= OBSTRUCTION_CONFIRM_CHECKS

    blocked = [(n, r) for n, r in result["path_results"].items()
               if r.get("confirmed_blocked")]

    result["blocked_paths"] = len(blocked)
    result["block_detail"] = "; ".join(
        f"{n} terhalang {int(r['blocked_ratio'] * 100)}%" for n, r in blocked
    )

    parts = list(result["person_labels"])
    if result["block_detail"]:
        parts.append(result["block_detail"])

    result["is_violation"] = bool(parts)
    result["detail"] = "; ".join(parts) if parts else "Semua aman"
    return result


# --------------------------------------------------------------------------
# Penggambaran
# --------------------------------------------------------------------------

def _render(frame, camera, result):
    """Gambar zona, jalur, dan kotak orang di atas salinan frame."""
    annotated = frame.copy()

    zones = camera.get("zones", [])
    paths = camera.get("access_paths", [])

    if zones:
        annotated = draw_zones(annotated, zones)
    if paths:
        annotated = draw_paths(annotated, paths, result["path_results"])

    for p in result["per_person"]:
        x1, y1, x2, y2 = p["bbox"]
        color = (0, 0, 255) if p["violation"] else (0, 200, 0)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        cv2.putText(annotated, p["text"], (x1, max(y1 - 8, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        cv2.circle(annotated, p["foot"], 4, color, -1)

    return annotated


# --------------------------------------------------------------------------
# Antarmuka publik
# --------------------------------------------------------------------------

def score(result):
    """
    Skor keparahan untuk memilih frame terburuk dalam satu siklus.
    Zona terlarang dan jalur terhalang diberi bobot lebih tinggi karena
    risikonya lebih langsung.
    """
    blocked_now = sum(
        1 for r in result.get("path_results", {}).values() if r.get("is_blocked")
    )
    return (
        result["no_helmet"]
        + result["no_vest"]
        + result["in_zone"] * 2
        + blocked_now * 3
    )


def analyze_frames(frames, camera, track_state=True):
    """
    Proses satu siklus pengecekan yang terdiri dari beberapa frame.

    Frame terburuk yang dipilih jadi bukti, dan status jalur diperbarui
    sekali saja untuk siklus ini.

    Return: (frame_beranotasi, hasil_dict)
    """
    best_frame = None
    best_result = None

    for frame in frames:
        result, _ = _evaluate(frame, camera)
        if best_result is None or score(result) > score(best_result):
            best_frame, best_result = frame, result

    if best_result is None:
        return None, None

    if track_state:
        _commit_path_state(camera, best_result)

    return _render(best_frame, camera, best_result), best_result


def analyze(frame, camera, track_state=True):
    """Versi satu frame. Berguna untuk pengujian dan pemakaian sederhana."""
    return analyze_frames([frame], camera, track_state)
