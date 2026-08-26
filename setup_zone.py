"""
setup_zone.py
Bantu menentukan koordinat zona terlarang untuk tiap kamera.

Zona harus disesuaikan dengan sudut pandang kamera masing-masing, jadi
langkah ini wajib dilakukan sekali per kamera setelah CCTV terpasang.

Dua mode:

1. Ambil gambar referensi (jalan di mini PC, tanpa perlu layar):
       python setup_zone.py --grab
   Gambar tersimpan di data/reference/. Salin ke laptop, lalu jalankan
   mode kedua di laptop tersebut.

2. Tentukan zona dengan klik (butuh layar/GUI):
       python setup_zone.py --draw data/reference/cam1.jpg

   Klik titik-titik sudut zona, tekan 's' untuk cetak koordinat,
   'r' untuk reset, 'q' untuk keluar. Salin hasilnya ke CAMERAS
   di config.py pada bagian "zones".
"""

import argparse
import os

import cv2
import numpy as np

from capture import grab_frame
from config import CAMERAS, DATA_DIR

REFERENCE_DIR = os.path.join(DATA_DIR, "reference")
points = []


def grab_references():
    """Ambil satu frame dari tiap kamera, simpan sebagai gambar referensi."""
    os.makedirs(REFERENCE_DIR, exist_ok=True)
    for cam in CAMERAS:
        print(f"Mengambil gambar dari {cam['name']} ({cam['id']})...")
        frame = grab_frame(cam["rtsp_url"])
        if frame is None:
            print(f"  GAGAL - kamera tidak terjangkau\n")
            continue
        path = os.path.join(REFERENCE_DIR, f"{cam['id']}.jpg")
        cv2.imwrite(path, frame)
        h, w = frame.shape[:2]
        print(f"  Tersimpan: {path} ({w}x{h})\n")

    print("Selesai. Salin folder ini ke komputer berlayar, lalu jalankan:")
    print("  python setup_zone.py --draw <file gambar>")


def mouse_callback(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        points.append((x, y))
        print(f"Titik ditambahkan: ({x}, {y})")


def draw_zone(image_path):
    """Tentukan polygon zona dengan cara klik di gambar referensi."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Gambar tidak ditemukan: {image_path}")

    window = "Klik sudut zona  (s=cetak, r=reset, q=keluar)"
    cv2.namedWindow(window)
    cv2.setMouseCallback(window, mouse_callback)

    print("\nKlik titik-titik sudut zona terlarang secara berurutan.")
    print("Tekan 's' untuk mencetak koordinat, 'r' untuk reset, 'q' untuk keluar.\n")

    while True:
        display = img.copy()
        if len(points) > 2:
            overlay = display.copy()
            cv2.fillPoly(overlay, [np.array(points, dtype=np.int32)], (0, 0, 255))
            cv2.addWeighted(overlay, 0.25, display, 0.75, 0, display)
        for p in points:
            cv2.circle(display, p, 4, (0, 0, 255), -1)
        if len(points) > 1:
            cv2.polylines(display, [np.array(points, dtype=np.int32)],
                          isClosed=True, color=(0, 0, 255), thickness=2)

        cv2.imshow(window, display)
        key = cv2.waitKey(1) & 0xFF

        if key == ord("s"):
            print("\nSalin baris ini ke config.py, ke dalam \"zones\" kamera terkait:")
            print(f'  {{"name": "Zona Baru", "polygon": {points}}}\n')
        elif key == ord("r"):
            points.clear()
            print("Titik direset.")
        elif key == ord("q"):
            break

    cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="Setup zona terlarang per kamera")
    parser.add_argument("--grab", action="store_true",
                         help="Ambil gambar referensi dari semua kamera")
    parser.add_argument("--draw", metavar="GAMBAR",
                         help="Tentukan zona dengan klik pada gambar referensi")
    args = parser.parse_args()

    if args.grab:
        grab_references()
    elif args.draw:
        draw_zone(args.draw)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
