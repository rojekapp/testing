"""
setup_path.py
Kelola jalur akses (jalur evakuasi / pintu darurat) yang harus selalu
bersih dari material.

Alurnya tiga langkah:

1. Tentukan polygon jalur — sama seperti zona terlarang:
       python setup_zone.py --grab
       python setup_zone.py --draw data/reference/cam1.jpg
   Salin hasilnya ke bagian "access_paths" di config.py.

2. Ambil baseline saat jalur BENAR-BENAR BERSIH:
       python setup_path.py --baseline
   Ini langkah paling menentukan. Sistem membandingkan kondisi
   sekarang dengan foto ini, jadi pastikan saat pengambilan tidak ada
   material, kendaraan, atau tumpukan apa pun di jalur.

3. Uji hasilnya (opsional tapi disarankan):
       python setup_path.py --check
   Menampilkan berapa persen tiap jalur terbaca terhalang saat ini.
   Kalau jalur bersih tapi terbaca >10%, baseline perlu diambil ulang
   atau ambang batas di config.py perlu disesuaikan.

Ambil baseline ulang setiap kali kondisi jalur berubah permanen
(pagar dipindah, jalur dicor, penerangan diganti).
"""

import argparse

from analyzer import get_detector
from capture import grab_frame
from config import CAMERAS, OBSTRUCTION_MIN_AREA_RATIO
from obstruction import check_path, load_baseline, save_baseline


def take_baselines(camera_filter=None):
    """Ambil foto baseline untuk semua jalur akses."""
    print("PENTING: pastikan semua jalur dalam kondisi bersih sebelum lanjut.\n")

    found_any = False
    for cam in CAMERAS:
        if camera_filter and cam["id"] != camera_filter:
            continue
        paths = cam.get("access_paths", [])
        if not paths:
            continue

        found_any = True
        print(f"{cam['name']} ({cam['id']})")
        frame = grab_frame(cam["rtsp_url"])
        if frame is None:
            print("  GAGAL - kamera tidak terjangkau\n")
            continue

        for p in paths:
            path = save_baseline(frame, cam["id"], p["name"])
            print(f"  Baseline '{p['name']}' tersimpan: {path}")
        print()

    if not found_any:
        print("Tidak ada jalur akses yang dikonfigurasi.")
        print("Isi dulu \"access_paths\" di config.py untuk kamera terkait.")
        return

    print("Selesai. Uji hasilnya dengan: python setup_path.py --check")


def check_paths(camera_filter=None):
    """Cek kondisi jalur saat ini terhadap baseline, tanpa mengubah status di DB."""
    detector = get_detector()

    for cam in CAMERAS:
        if camera_filter and cam["id"] != camera_filter:
            continue
        paths = cam.get("access_paths", [])
        if not paths:
            continue

        print(f"\n{cam['name']} ({cam['id']})")
        frame = grab_frame(cam["rtsp_url"])
        if frame is None:
            print("  GAGAL - kamera tidak terjangkau")
            continue

        person_boxes = [d["bbox"] for d in detector.detect(frame)]
        if person_boxes:
            print(f"  ({len(person_boxes)} orang terdeteksi, areanya dikecualikan)")

        for p in paths:
            baseline = load_baseline(cam["id"], p["name"])
            res = check_path(frame, baseline, p["polygon"], person_boxes)

            if res.get("error"):
                print(f"  [!] {p['name']}: {res['error']}")
                continue

            persen = res["blocked_ratio"] * 100
            ambang = OBSTRUCTION_MIN_AREA_RATIO * 100
            status = "TERHALANG" if res["is_blocked"] else "bersih"
            print(f"  [{status:>9}] {p['name']}: {persen:.1f}% terisi (ambang {ambang:.0f}%)")

    print("\nCatatan: hasil di atas adalah pembacaan sesaat. Saat service berjalan,")
    print("halangan baru dilaporkan setelah bertahan beberapa kali pengecekan.")


def main():
    parser = argparse.ArgumentParser(description="Kelola baseline jalur akses")
    parser.add_argument("--baseline", action="store_true",
                         help="Ambil baseline jalur bersih dari semua kamera")
    parser.add_argument("--check", action="store_true",
                         help="Cek kondisi jalur saat ini terhadap baseline")
    parser.add_argument("--camera", metavar="ID",
                         help="Batasi ke satu kamera saja (mis. cam1)")
    args = parser.parse_args()

    if args.baseline:
        take_baselines(args.camera)
    elif args.check:
        check_paths(args.camera)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
