"""
monitor.py
Service utama Safety Monitor CCTV. Jalan terus di background pada
PC/mini PC lokasi, mengambil gambar dari tiap kamera secara berkala,
menganalisis, lalu menyimpan hasilnya di host.

Cara pakai:
    python monitor.py                  # jalan sebagai service (loop terus)
    python monitor.py --once           # satu siklus saja, untuk tes
    python monitor.py --test-cameras   # cek koneksi semua kamera
"""

import argparse
import signal
import sys
import time
from datetime import datetime

from analyzer import analyze, score, get_detector
from capture import grab_frames, test_camera
from config import (
    CAMERAS, CAPTURE_INTERVAL_SECONDS, FRAMES_PER_CHECK, FRAME_GAP_SECONDS,
    ACTIVE_HOURS_START, ACTIVE_HOURS_END, SAVE_ONLY_VIOLATIONS,
)
from storage import (
    init_storage, save_snapshot, log_detection, cleanup_old_data, disk_usage_mb,
)

running = True


def handle_shutdown(signum, frame):
    """Supaya Ctrl+C atau systemd stop berhenti dengan rapi, bukan putus di tengah."""
    global running
    print("\n[monitor] Menerima sinyal berhenti, menutup service...")
    running = False


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


def in_active_hours(now=None):
    now = now or datetime.now()
    if ACTIVE_HOURS_START == 0 and ACTIVE_HOURS_END >= 24:
        return True
    return ACTIVE_HOURS_START <= now.hour < ACTIVE_HOURS_END


def check_camera(camera):
    """Satu siklus pengecekan untuk satu kamera."""
    timestamp = datetime.now()
    frames = grab_frames(camera["rtsp_url"], FRAMES_PER_CHECK, FRAME_GAP_SECONDS)

    if not frames:
        print(f"[{timestamp:%H:%M:%S}] {camera['name']}: kamera tidak terjangkau")
        return

    # Analisis semua frame, ambil yang paling banyak pelanggarannya
    best_frame = None
    best_result = None
    for frame in frames:
        annotated, result = analyze(frame, camera.get("zones", []))
        if best_result is None or score(result) > score(best_result):
            best_frame, best_result = annotated, result

    snapshot_path = None
    if best_result["is_violation"] or not SAVE_ONLY_VIOLATIONS:
        snapshot_path = save_snapshot(best_frame, camera["id"], timestamp)

    log_detection(camera["id"], camera["name"], best_result, snapshot_path, timestamp)

    status = "PELANGGARAN" if best_result["is_violation"] else "aman"
    print(f"[{timestamp:%H:%M:%S}] {camera['name']}: "
          f"{best_result['person_count']} orang - {status} - {best_result['detail']}")


def run_cycle():
    for camera in CAMERAS:
        if not running:
            break
        try:
            check_camera(camera)
        except Exception as e:
            # Satu kamera bermasalah tidak boleh menjatuhkan seluruh service
            print(f"[monitor] Error pada {camera['name']}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Safety Monitor CCTV")
    parser.add_argument("--once", action="store_true", help="Jalankan satu siklus lalu keluar")
    parser.add_argument("--test-cameras", action="store_true", help="Cek koneksi semua kamera")
    args = parser.parse_args()

    if args.test_cameras:
        print("Mengecek koneksi kamera...\n")
        for cam in CAMERAS:
            ok, msg = test_camera(cam["rtsp_url"])
            mark = "OK  " if ok else "GAGAL"
            print(f"  [{mark}] {cam['name']} ({cam['id']}): {msg}")
        return

    init_storage()
    print("[monitor] Memuat model deteksi...")
    get_detector()
    print(f"[monitor] Siap. {len(CAMERAS)} kamera, cek tiap {CAPTURE_INTERVAL_SECONDS} detik.")
    print(f"[monitor] Jam aktif: {ACTIVE_HOURS_START:02d}:00 - {ACTIVE_HOURS_END:02d}:00")

    if args.once:
        run_cycle()
        return

    last_cleanup_day = None

    while running:
        cycle_start = time.time()

        if in_active_hours():
            run_cycle()
        else:
            print(f"[{datetime.now():%H:%M:%S}] Di luar jam aktif, capture dilewati.")

        # Bersih-bersih data lama sekali sehari
        today = datetime.now().date()
        if last_cleanup_day != today:
            removed = cleanup_old_data()
            if removed:
                print(f"[monitor] Membersihkan {removed} folder snapshot lama.")
            print(f"[monitor] Pemakaian disk saat ini: {disk_usage_mb()} MB")
            last_cleanup_day = today

        # Tidur sisa interval, tapi tetap responsif terhadap sinyal berhenti
        elapsed = time.time() - cycle_start
        remaining = max(0, CAPTURE_INTERVAL_SECONDS - elapsed)
        slept = 0
        while slept < remaining and running:
            time.sleep(min(1, remaining - slept))
            slept += 1

    print("[monitor] Service berhenti.")
    sys.exit(0)


if __name__ == "__main__":
    main()
