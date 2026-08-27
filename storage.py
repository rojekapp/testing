"""
storage.py
Penyimpanan hasil deteksi di host (PC/mini PC lokasi):
- Metadata pelanggaran  -> SQLite (data/safety.db)
- Gambar bukti          -> JPEG (data/snapshots/YYYY-MM-DD/)
- Pembersihan otomatis  -> hapus snapshot lebih tua dari RETENTION_DAYS

Semua data tetap di mesin lokal, tidak dikirim ke mana pun.
"""

import os
import shutil
import sqlite3
from datetime import datetime, timedelta

import cv2

from config import (
    DATA_DIR, SNAPSHOT_DIR, DB_PATH, JPEG_QUALITY, RETENTION_DAYS,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS detections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL,
    camera_id     TEXT NOT NULL,
    camera_name   TEXT NOT NULL,
    person_count  INTEGER NOT NULL,
    no_helmet     INTEGER NOT NULL,
    no_vest       INTEGER NOT NULL,
    in_zone       INTEGER NOT NULL,
    is_violation  INTEGER NOT NULL,
    blocked_paths INTEGER NOT NULL DEFAULT 0,
    block_detail  TEXT DEFAULT '',
    detail        TEXT,
    snapshot_path TEXT
);

-- Status jalur disimpan di DB (bukan di memori) supaya hitungan
-- "terdeteksi berapa kali berturut-turut" tidak hilang saat service restart.
CREATE TABLE IF NOT EXISTS path_state (
    camera_id    TEXT NOT NULL,
    path_name    TEXT NOT NULL,
    consecutive  INTEGER NOT NULL DEFAULT 0,
    last_ratio   REAL NOT NULL DEFAULT 0,
    first_seen   TEXT,
    updated_at   TEXT,
    PRIMARY KEY (camera_id, path_name)
);
CREATE INDEX IF NOT EXISTS idx_detections_time ON detections(timestamp);
CREATE INDEX IF NOT EXISTS idx_detections_cam  ON detections(camera_id);
"""


def init_storage():
    """Buat folder data dan tabel database kalau belum ada."""
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    # Database dari versi sebelum fitur deteksi halangan belum punya kolom ini
    existing = {r[1] for r in conn.execute("PRAGMA table_info(detections)")}
    if "blocked_paths" not in existing:
        conn.execute("ALTER TABLE detections ADD COLUMN blocked_paths INTEGER NOT NULL DEFAULT 0")
    if "block_detail" not in existing:
        conn.execute("ALTER TABLE detections ADD COLUMN block_detail TEXT DEFAULT ''")

    conn.commit()
    conn.close()


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def save_snapshot(frame, camera_id, timestamp):
    """Simpan frame sebagai JPEG, dikelompokkan per tanggal. Return path relatif."""
    day_folder = timestamp.strftime("%Y-%m-%d")
    folder = os.path.join(SNAPSHOT_DIR, day_folder)
    os.makedirs(folder, exist_ok=True)

    filename = f"{camera_id}_{timestamp.strftime('%H%M%S')}.jpg"
    full_path = os.path.join(folder, filename)
    cv2.imwrite(full_path, frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])

    return os.path.join(day_folder, filename)


def log_detection(camera_id, camera_name, result, snapshot_path, timestamp):
    """Catat satu hasil pengecekan ke database."""
    conn = _connect()
    conn.execute(
        """INSERT INTO detections
           (timestamp, camera_id, camera_name, person_count, no_helmet,
            no_vest, in_zone, is_violation, blocked_paths, block_detail,
            detail, snapshot_path)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            camera_id,
            camera_name,
            result["person_count"],
            result["no_helmet"],
            result["no_vest"],
            result["in_zone"],
            1 if result["is_violation"] else 0,
            result.get("blocked_paths", 0),
            result.get("block_detail", ""),
            result["detail"],
            snapshot_path or "",
        ),
    )
    conn.commit()
    conn.close()


def get_recent(limit=100, only_violations=False, camera_id=None):
    """Ambil deteksi terbaru untuk ditampilkan di dashboard."""
    query = "SELECT * FROM detections WHERE 1=1"
    params = []
    if only_violations:
        query += " AND is_violation = 1"
    if camera_id:
        query += " AND camera_id = ?"
        params.append(camera_id)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    conn = _connect()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_daily_summary(days=7):
    """Ringkasan jumlah pelanggaran per hari, untuk grafik dashboard."""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = _connect()
    rows = conn.execute(
        """SELECT substr(timestamp, 1, 10) AS tanggal,
                  COUNT(*) AS total_cek,
                  SUM(is_violation) AS total_pelanggaran
           FROM detections
           WHERE substr(timestamp, 1, 10) >= ?
           GROUP BY tanggal
           ORDER BY tanggal""",
        (since,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def cleanup_old_data():
    """Hapus folder snapshot yang lebih tua dari RETENTION_DAYS, dan baris DB terkait."""
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    removed = 0

    if os.path.isdir(SNAPSHOT_DIR):
        for folder_name in os.listdir(SNAPSHOT_DIR):
            folder_path = os.path.join(SNAPSHOT_DIR, folder_name)
            if not os.path.isdir(folder_path):
                continue
            try:
                datetime.strptime(folder_name, "%Y-%m-%d")
            except ValueError:
                continue  # bukan folder tanggal, lewati
            if folder_name < cutoff_str:
                shutil.rmtree(folder_path, ignore_errors=True)
                removed += 1

    conn = _connect()
    conn.execute("DELETE FROM detections WHERE substr(timestamp, 1, 10) < ?", (cutoff_str,))
    conn.commit()
    conn.execute("VACUUM")
    conn.close()

    return removed


def disk_usage_mb():
    """Total ukuran folder data, supaya bisa dipantau dari dashboard."""
    total = 0
    for root, _, files in os.walk(DATA_DIR):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return round(total / (1024 * 1024), 1)


def bump_path_state(camera_id, path_name, is_blocked, ratio):
    """
    Perbarui hitungan berapa kali berturut-turut satu jalur terdeteksi terhalang.

    Return (consecutive, first_seen):
        consecutive = jumlah pengecekan berturut-turut jalur ini terhalang.
                      Kembali ke 0 begitu jalur terlihat bersih.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _connect()
    row = conn.execute(
        "SELECT consecutive, first_seen FROM path_state WHERE camera_id = ? AND path_name = ?",
        (camera_id, path_name),
    ).fetchone()

    if is_blocked:
        consecutive = (row["consecutive"] if row else 0) + 1
        first_seen = (row["first_seen"] if row and row["consecutive"] > 0 else None) or now
    else:
        consecutive = 0
        first_seen = None

    conn.execute(
        """INSERT INTO path_state (camera_id, path_name, consecutive, last_ratio, first_seen, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(camera_id, path_name) DO UPDATE SET
               consecutive = excluded.consecutive,
               last_ratio  = excluded.last_ratio,
               first_seen  = excluded.first_seen,
               updated_at  = excluded.updated_at""",
        (camera_id, path_name, consecutive, ratio, first_seen, now),
    )
    conn.commit()
    conn.close()
    return consecutive, first_seen


def get_blocked_paths():
    """Daftar jalur yang saat ini sedang terhalang, untuk ringkasan dashboard."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM path_state WHERE consecutive > 0 ORDER BY consecutive DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
