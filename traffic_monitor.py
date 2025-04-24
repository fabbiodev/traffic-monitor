import os
import time
import threading
import sqlite3
import datetime

from flask import Flask, render_template, jsonify, request, url_for
import psutil

app = Flask(__name__)
BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, 'traffic.db')

# — Инициализация БД —
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS traffic (
            timestamp DATETIME,
            incoming INTEGER,
            outgoing INTEGER
        )
    ''')
    conn.commit()
    return conn

db_conn = init_db()
previous = psutil.net_io_counters()
traffic_data = {'in': 0, 'out': 0}

# — Фоновый сбор трафика и запись в БД —
def update_traffic():
    global previous, traffic_data
    cur = db_conn.cursor()
    while True:
        time.sleep(1)
        now = datetime.datetime.utcnow()
        cnt = psutil.net_io_counters()
        inc = cnt.bytes_recv - previous.bytes_recv
        out = cnt.bytes_sent - previous.bytes_sent
        previous = cnt
        traffic_data = {'in': inc, 'out': out}

        cur.execute(
            'INSERT INTO traffic (timestamp, incoming, outgoing) VALUES (?,?,?)',
            (now, inc, out)
        )
        db_conn.commit()

# — Утилиты —
def format_bps(v):
    if v >= 1024**2:
        return f"{v/1024**2:.2f} MB/s"
    if v >= 1024:
        return f"{v/1024:.2f} KB/s"
    return f"{v} B/s"

def get_lang():
    a = request.headers.get('Accept-Language', '').lower()
    return 'ru' if a.startswith('ru') else 'en'

texts = {
    'en': {
        'home': 'Home',
        'stats': 'Statistics',
        'incoming': 'Incoming',
        'outgoing': 'Outgoing',
        'hour': 'Hour',
        'avg_speed': 'Average Speed',
        'total': 'Total Traffic',
        'today': 'Today',
        'yesterday': 'Yesterday'
    },
    'ru': {
        'home': 'Главная',
        'stats': 'Статистика',
        'incoming': 'Входящий',
        'outgoing': 'Исходящий',
        'hour': 'Час',
        'avg_speed': 'Сред. скорость',
        'total': 'Всего трафика',
        'today': 'Сегодня',
        'yesterday': 'Вчера'
    }
}

# — Маршруты —
@app.route('/')
def index():
    lang = get_lang()
    return render_template('index.html',
        incoming=format_bps(traffic_data['in']),
        outgoing=format_bps(traffic_data['out']),
        texts=texts[lang],
        lang=lang
    )

@app.route('/stats')
def stats():
    lang = get_lang()
    cur = db_conn.cursor()
    now = datetime.datetime.utcnow()

    def query(day_delta):
        d = (now - datetime.timedelta(days=day_delta)).date()
        start = datetime.datetime.combine(d, datetime.time.min)
        end   = datetime.datetime.combine(d, datetime.time.max)
        cur.execute('''
            SELECT 
              strftime('%H', timestamp) AS hour,
              AVG(incoming) AS avg_in,
              SUM(incoming) AS tot_in,
              AVG(outgoing) AS avg_out,
              SUM(outgoing) AS tot_out
            FROM traffic
            WHERE timestamp BETWEEN ? AND ?
            GROUP BY hour
            ORDER BY hour
        ''', (start, end))
        return cur.fetchall()

    yesterday = query(1)
    today     = query(0)
    return render_template('stats.html',
        yesterday=yesterday,
        today=today,
        texts=texts[lang],
        lang=lang
    )

@app.route('/api')
def api():
    return jsonify({
        'incoming': traffic_data['in'],
        'outgoing': traffic_data['out'],
        'incoming_human': format_bps(traffic_data['in']),
        'outgoing_human': format_bps(traffic_data['out'])
    })

if __name__ == '__main__':
    threading.Thread(target=update_traffic, daemon=True).start()
    app.run(host='0.0.0.0', port=5001)
