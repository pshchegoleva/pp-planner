"""
Python-сервер для 24/7 уведомлений.
Запуск:
  pip install flask apscheduler requests
  python server.py
"""
import json, os, requests
from datetime import datetime
from flask import Flask, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
TG_TOKEN = os.getenv('TG_TOKEN', '8629848748:AAGFpZlyRnowdS5lwxA6UclHnKsSeYI3kP8')
TG_CHAT = os.getenv('TG_CHAT', '1366750627')

app = Flask(__name__)
DATA_FILE = 'planner_data.json'

def load_data():
    if not os.path.exists(DATA_FILE):
        return {'tasks':[], 'settings':{'tgToken':'', 'tgChat':''}}
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_data(d):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def send_tg(text):
    d = load_data()
    token = d.get('settings',{}).get('tgToken','')
    chat = d.get('settings',{}).get('tgChat','')
    if not token or not chat:
        print('TG не настроен')
        return
    try:
        r = requests.post(f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat, 'text': text}, timeout=10)
        print('TG:', r.status_code, r.text[:100])
    except Exception as e:
        print('TG ошибка:', e)

def morning_briefing():
    d = load_data()
    today = datetime.now().strftime('%Y-%m-%d')
    tasks = [t for t in d.get('tasks',[]) if not t.get('done') and t.get('scheduledDate') == today]
    h = sum(float(t.get('hours',0)) for t in tasks)
    msg = f"🌿 Доброе утро!\n\nСегодня: {len(tasks)} задач • {h}ч\n\n"
    for t in tasks:
        msg += f"• {t['title']} — {t['hours']}ч\n"
    send_tg(msg)

def evening_report():
    d = load_data()
    today = datetime.now().strftime('%Y-%m-%d')
    done = [t for t in d.get('tasks',[]) if t.get('done') and t.get('doneAt') == today]
    send_tg(f"🌙 Итоги дня\n\n✅ Выполнено: {len(done)} задач")

def deadline_check():
    d = load_data()
    today = datetime.now().strftime('%Y-%m-%d')
    for t in d.get('tasks',[]):
        if t.get('done'): continue
        dl = t.get('deadline','')
        if dl == today:
            send_tg(f"⏰ Сегодня сдать: {t['title']}")
        elif dl < today:
            send_tg(f"🚨 Просрочено: {t['title']} (было {dl})")

# Планировщик
scheduler = BackgroundScheduler()
scheduler.add_job(morning_briefing, 'cron', hour=8, minute=0)
scheduler.add_job(evening_report, 'cron', hour=21, minute=0)
scheduler.add_job(deadline_check, 'cron', hour=9, minute=0)
scheduler.start()

# API для синхронизации с браузером
@app.route('/api/data', methods=['GET'])
def get_data():
    return jsonify(load_data())

@app.route('/api/data', methods=['POST'])
def post_data():
    save_data(request.json)
    return jsonify({'ok': True})

@app.route('/api/send', methods=['POST'])
def manual_send():
    send_tg(request.json.get('text',''))
    return jsonify({'ok': True})

if __name__ == '__main__':
    import os
    port = int(os.getenv('PORT', 5000))
    print(f'🌿 Сервер запущен на порту {port}')
    app.run(host='0.0.0.0', port=port, debug=False)
