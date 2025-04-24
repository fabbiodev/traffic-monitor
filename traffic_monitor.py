import os
import time
import threading
import sqlite3
import datetime

from flask import Flask, render_template, jsonify, request
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

# — Сбор и запись трафика —
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

# — Форматирование в удобные единицы —
def format_bps(v):
    if v >= 1024**2:
        return f"{v/1024**2:.2f} MB/s"
    if v >= 1024:
        return f"{v/1024:.2f} KB/s"
    return f"{v} B/s"

def format_bytes(v):
    if v >= 1024**3:
        return f"{v/1024**3:.2f} GB"
    if v >= 1024**2:
        return f"{v/1024**2:.2f} MB"
    if v >= 1024:
        return f"{v/1024:.2f} KB"
    return f"{v} B"

# — Определение языка по заголовку —
def get_lang():
    a = request.headers.get('Accept-Language', '').lower()
    return 'ru' if a.startswith('ru') else 'en'

texts = {
    'en': {
        'home': 'Home',   'stats': 'Statistics',
        'incoming': 'Incoming', 'outgoing': 'Outgoing',
        'hour': 'Hour',   'avg_speed': 'Avg Speed', 'total': 'Total',
        'today': 'Today', 'yesterday': 'Yesterday'
    },
    'ru': {
        'home': 'Главная', 'stats': 'Статистика',
        'incoming': 'Входящий', 'outgoing': 'Исходящий',
        'hour': 'Час',    'avg_speed': 'Сред. скорость', 'total': 'Всего',
        'today': 'Сегодня', 'yesterday': 'Вчера'
    }
}

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
              AVG(incoming) AS ai, SUM(incoming) AS ti,
              AVG(outgoing) AS ao, SUM(outgoing) AS to
            FROM traffic
            WHERE timestamp BETWEEN ? AND ?
            GROUP BY hour
            ORDER BY hour
        ''', (start, end))
        rows = cur.fetchall()
        data = []
        for hr, ai, ti, ao, to in rows:
            data.append({
                'hour':    f"{hr}:00",
                'avg_in':  format_bps(ai),
                'tot_in':  format_bytes(ti),
                'avg_out': format_bps(ao),
                'tot_out': format_bytes(to),
            })
        return data

    return render_template('stats.html',
        yesterday=query(1),
        today=query(0),
        texts=texts[lang],
        lang=lang
    )

@app.route('/api')
def api():
    return jsonify({
        'incoming':       traffic_data['in'],
        'outgoing':       traffic_data['out'],
        'incoming_human': format_bps(traffic_data['in']),
        'outgoing_human': format_bps(traffic_data['out'])
    })

# — Запуск фонового потока мониторинга сразу при импорте модуля —
threading.Thread(target=update_traffic, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
