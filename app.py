import threading
import time
import sqlite3
from datetime import datetime, timedelta

import psutil
from flask import Flask, render_template, jsonify, request
from flask_babel import Babel, _

from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# --- Internationalization (Flask‑Babel ≥4) ---------------------------
def select_locale():
    # Pick best match from Accept‑Language header
    return request.accept_languages.best_match(app.config['LANGUAGES'])

babel = Babel(app, locale_selector=select_locale)
# ---------------------------------------------------------------------

# ---------- SQLite initialisation ------------------------------------
conn = sqlite3.connect(Config.DB_PATH, check_same_thread=False)
cur = conn.cursor()
cur.execute('''
    CREATE TABLE IF NOT EXISTS hourly_traffic (
        hour TEXT PRIMARY KEY,
        bytes_sent INTEGER,
        bytes_recv INTEGER
    )
''')
conn.commit()

# ---------- Runtime state --------------------------------------------
last_snapshot = psutil.net_io_counters(pernic=True)
current_rates = {}     # {iface: {'sent': str, 'recv': str}}

# ---------- Helpers --------------------------------------------------
UNITS = ('B', 'KB', 'MB', 'GB', 'TB')

def human(num):
    for u in UNITS:
        if num < 1024:
            return f"{num:.2f} {u}"
        num /= 1024
    return f"{num:.2f} PB"

# ---------- Routes ---------------------------------------------------
@app.get('/')
def index():
    return render_template('index.html')

@app.get('/stats')
def stats():
    return render_template('stats.html')

@app.get('/api/current')
def api_current():
    return jsonify(current_rates)

@app.get('/api/stats')
def api_stats():
    out = []
    now = datetime.now()
    for day in [now.date() - timedelta(days=1), now.date()]:
        for h in range(24):
            hour_dt = datetime.combine(day, datetime.min.time()) + timedelta(hours=h)
            key = hour_dt.strftime('%Y-%m-%d %H:00:00')
            cur = conn.cursor()
            cur.execute('SELECT bytes_sent, bytes_recv FROM hourly_traffic WHERE hour=?', (key,))
            row = cur.fetchone()
            sent = row[0] if row else 0
            recv = row[1] if row else 0
            out.append({
                'hour': key,
                'total_sent': human(sent),
                'total_recv': human(recv),
                'avg_sent': human(sent / 3600),
                'avg_recv': human(recv / 3600)
            })
    return jsonify(out)

# ---------- Background collector ------------------------------------
def collector():
    global last_snapshot
    while True:
        time.sleep(1)
        snap = psutil.net_io_counters(pernic=True)
        now = datetime.now()
        for iface, stats in snap.items():
            prev = last_snapshot.get(iface)
            if not prev:
                continue
            sent_d = stats.bytes_sent - prev.bytes_sent
            recv_d = stats.bytes_recv - prev.bytes_recv
            current_rates[iface] = {'sent': human(sent_d), 'recv': human(recv_d)}

            hour_key = now.replace(minute=0, second=0, microsecond=0).strftime('%Y-%m-%d %H:00:00')
            cur = conn.cursor()
            cur.execute('INSERT INTO hourly_traffic(hour, bytes_sent, bytes_recv) VALUES(?,?,?) '
                        'ON CONFLICT(hour) DO UPDATE SET '
                        'bytes_sent = bytes_sent + excluded.bytes_sent, '
                        'bytes_recv = bytes_recv + excluded.bytes_recv',
                        (hour_key, sent_d, recv_d))
            conn.commit()

        last_snapshot = snap

threading.Thread(target=collector, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
