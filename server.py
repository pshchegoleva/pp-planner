"""
Python-сервер для 24/7 уведомлений.
Railway-совместимая версия с CORS.
"""
import json
import os
import requests
from datetime import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)
DATA_FILE = 'planner_data.json'

TG_TOKEN = os.getenv('TG_TOKEN', '')
TG_CHAT = os.getenv('TG_CHAT', '')

# ========== CORS — РАЗРЕШАЕМ ЗАПРОСЫ ИЗ БРАУЗЕРА ==========
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.route('/api/data', methods=['OPTIONS'])
def options_data():
    return '', 204
# ============================================================

def load_data():
    try:
        if not os.path.exists(DATA_FILE):
            return {'tasks':[], 'settings':{'tgToken':TG_TOKEN, 'tgChat':TG_CHAT}}
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f'Ошибка загрузки: {e}')
        return {'tasks':[], 'settings':{'tgToken':TG_TOKEN, 'tgChat':TG_CHAT}}

def save_data(d):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'Ошибка сохранения: {e}')

def send_tg(text):
    if not TG_TOKEN or not TG_CHAT:
        print('TG не настроен')
        return False
    try:
        r = requests.post(
            f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage',
            json={'chat_id': TG_CHAT, 'text': text},
            timeout=10
        )
        print(f'TG: {r.status_code}')
        return r.ok
    except Exception as e:
        print(f'TG ошибка: {e}')
        return False

def morning_briefing():
    try:
        d = load_data()
        today = datetime.now().strftime('%Y-%m-%d')
        tasks = [t for t in d.get('tasks',[]) if not t.get('done') and t.get('scheduledDate') == today]
        h = sum(float(t.get('hours',0)) for t in tasks)
        msg = f"🌿 Доброе утро!\n\nСегодня: {len(tasks)} задач • {h}ч\n\n"
        for t in tasks:
            msg += f"• {t['title']} — {t['hours']}ч\n"
        send_tg(msg)
    except Exception as e:
        print(f'Ошибка: {e}')

def evening_report():
    try:
        d = load_data()
        today = datetime.now().strftime('%Y-%m-%d')
        done = [t for t in d.get('tasks',[]) if t.get('done') and t.get('doneAt') == today]
        send_tg(f"🌙 Итоги дня\n\n✅ Выполнено: {len(done)} задач")
    except Exception as e:
        print(f'Ошибка: {e}')

def deadline_check():
    try:
        d = load_data()
        today = datetime.now().strftime('%Y-%m-%d')
        for t in d.get('tasks',[]):
            if t.get('done'): continue
            dl = t.get('deadline','')
            if dl == today:
                send_tg(f"⏰ Сегодня сдать: {t['title']}")
            elif dl < today:
                send_tg(f"🚨 Просрочено: {t['title']}")
    except Exception as e:
        print(f'Ошибка: {e}')

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
        # Утро
    scheduler.add_job(morning_briefing, 'cron', hour=8, minute=0)
    # Дедлайны — 2 раза в день
    scheduler.add_job(deadline_check, 'cron', hour=9, minute=0)
    scheduler.add_job(deadline_check, 'cron', hour=14, minute=0)
    # Вечер — 1 раз
    scheduler.add_job(evening_report, 'cron', hour=21, minute=0)
    scheduler.start()
    print('✅ Планировщик запущен')
except Exception as e:
    print(f'Ошибка планировщика: {e}')

@app.route('/')
def index():
    return jsonify({
        'status': 'ok',
        'message': '🌿 Сервер работает',
        'tg_configured': bool(TG_TOKEN and TG_CHAT)
    })

@app.route('/api/data', methods=['GET'])
def get_data():
    return jsonify(load_data())

@app.route('/api/data', methods=['POST'])
def post_data():
    try:
        save_data(request.json)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/send', methods=['POST'])
def manual_send():
    text = request.json.get('text', '')
    ok = send_tg(text)
    return jsonify({'ok': ok})

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f'🌿 Сервер запущен на порту {port}')
    app.run(host='0.0.0.0', port=port, debug=False)
