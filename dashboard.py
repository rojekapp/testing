"""
dashboard.py
Dashboard web sederhana untuk melihat hasil deteksi. Dijalankan di PC
yang sama dengan monitor.py, lalu dibuka dari HP/laptop lain di jaringan
yang sama: http://<ip-pc>:8080

Read-only: dashboard hanya membaca database yang diisi monitor.py.

Cara pakai:
    python dashboard.py
"""

import os

from flask import Flask, jsonify, render_template_string, request, send_from_directory

from config import CAMERAS, SNAPSHOT_DIR, DASHBOARD_HOST, DASHBOARD_PORT
from storage import init_storage, get_recent, get_daily_summary, disk_usage_mb

app = Flask(__name__)

TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Safety Monitor</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; font-family: system-ui, -apple-system, sans-serif;
           background: #f4f5f7; color: #1a1a1a; }
    header { background: #1f2933; color: #fff; padding: 16px 20px; }
    header h1 { margin: 0; font-size: 18px; }
    header p { margin: 4px 0 0; font-size: 13px; color: #9aa5b1; }
    .wrap { padding: 16px; max-width: 900px; margin: 0 auto; }
    .stats { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
    .stat { flex: 1 1 120px; background: #fff; border-radius: 8px; padding: 12px;
            border: 1px solid #e3e6ea; }
    .stat .val { font-size: 22px; font-weight: 600; }
    .stat .lbl { font-size: 12px; color: #6b7480; margin-top: 2px; }
    .filters { margin-bottom: 14px; display: flex; gap: 8px; flex-wrap: wrap; }
    .filters a { padding: 7px 13px; border-radius: 6px; text-decoration: none;
                 font-size: 13px; background: #fff; color: #1f2933;
                 border: 1px solid #e3e6ea; }
    .filters a.active { background: #1f2933; color: #fff; border-color: #1f2933; }
    .card { background: #fff; border: 1px solid #e3e6ea; border-radius: 8px;
            margin-bottom: 12px; overflow: hidden; }
    .card.violation { border-left: 4px solid #d64545; }
    .card.safe { border-left: 4px solid #3ba55d; }
    .card img { width: 100%; display: block; background: #000; }
    .meta { padding: 11px 13px; }
    .meta .top { display: flex; justify-content: space-between; gap: 8px;
                 font-size: 13px; margin-bottom: 5px; }
    .meta .cam { font-weight: 600; }
    .meta .time { color: #6b7480; }
    .meta .detail { font-size: 13px; color: #444; }
    .badge { display: inline-block; font-size: 11px; padding: 2px 7px;
             border-radius: 4px; margin-right: 4px; }
    .badge.red { background: #fce8e8; color: #a61b1b; }
    .badge.green { background: #e6f4ea; color: #1e6b39; }
    .empty { text-align: center; color: #6b7480; padding: 36px 12px; }
  </style>
</head>
<body>
  <header>
    <h1>Safety Monitor</h1>
    <p>{{ cameras|length }} kamera &middot; {{ disk }} MB terpakai</p>
  </header>
  <div class="wrap">
    <div class="stats">
      <div class="stat">
        <div class="val">{{ total_hari_ini }}</div>
        <div class="lbl">Pengecekan hari ini</div>
      </div>
      <div class="stat">
        <div class="val">{{ pelanggaran_hari_ini }}</div>
        <div class="lbl">Pelanggaran hari ini</div>
      </div>
      <div class="stat">
        <div class="val">{{ pelanggaran_minggu }}</div>
        <div class="lbl">Pelanggaran 7 hari</div>
      </div>
    </div>

    <div class="filters">
      <a href="/?filter=violations" class="{{ 'active' if f == 'violations' }}">Pelanggaran</a>
      <a href="/?filter=all" class="{{ 'active' if f == 'all' }}">Semua</a>
      {% for c in cameras %}
        <a href="/?filter={{ f }}&camera={{ c.id }}"
           class="{{ 'active' if cam == c.id }}">{{ c.name }}</a>
      {% endfor %}
    </div>

    {% if not rows %}
      <div class="empty">Belum ada data.</div>
    {% endif %}

    {% for r in rows %}
      <div class="card {{ 'violation' if r.is_violation else 'safe' }}">
        {% if r.snapshot_path %}
          <img src="/snapshot/{{ r.snapshot_path }}" loading="lazy" alt="bukti">
        {% endif %}
        <div class="meta">
          <div class="top">
            <span class="cam">{{ r.camera_name }}</span>
            <span class="time">{{ r.timestamp }}</span>
          </div>
          <div>
            {% if r.no_helmet %}<span class="badge red">{{ r.no_helmet }} tanpa helm</span>{% endif %}
            {% if r.no_vest %}<span class="badge red">{{ r.no_vest }} tanpa rompi</span>{% endif %}
            {% if r.in_zone %}<span class="badge red">{{ r.in_zone }} di zona terlarang</span>{% endif %}
            {% if not r.is_violation %}<span class="badge green">Aman</span>{% endif %}
          </div>
          <div class="detail">{{ r.person_count }} orang terdeteksi</div>
        </div>
      </div>
    {% endfor %}
  </div>
</body>
</html>
"""


@app.route("/")
def index():
    f = request.args.get("filter", "violations")
    cam = request.args.get("camera")

    rows = get_recent(limit=60, only_violations=(f == "violations"), camera_id=cam)
    summary = get_daily_summary(days=7)

    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    hari_ini = next((s for s in summary if s["tanggal"] == today), None)

    return render_template_string(
        TEMPLATE,
        rows=rows,
        cameras=CAMERAS,
        f=f,
        cam=cam,
        disk=disk_usage_mb(),
        total_hari_ini=hari_ini["total_cek"] if hari_ini else 0,
        pelanggaran_hari_ini=(hari_ini["total_pelanggaran"] or 0) if hari_ini else 0,
        pelanggaran_minggu=sum((s["total_pelanggaran"] or 0) for s in summary),
    )


@app.route("/snapshot/<path:filename>")
def snapshot(filename):
    return send_from_directory(os.path.abspath(SNAPSHOT_DIR), filename)


@app.route("/api/detections")
def api_detections():
    """Endpoint JSON, kalau nanti mau disambungkan ke sistem lain."""
    return jsonify(get_recent(
        limit=int(request.args.get("limit", 50)),
        only_violations=request.args.get("violations") == "1",
    ))


if __name__ == "__main__":
    init_storage()
    print(f"Dashboard jalan di http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    print("Buka dari HP/laptop lain pakai IP lokal PC ini, contoh: http://192.168.1.50:8080")
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False)
