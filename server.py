"""
Python-сервер для 24/7 уведомлений.
Railway-совместимая версия с отладкой.
"""
import json
import os
import sys
import requests
from datetime import datetime

print("=" * 50)
print("🌿 Сервер запускается...")
print(f"Python версия: {sys.version}")
print("=" * 50)

from flask import Flask, jsonify, request

print("✅ Flask импортирован")

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    print("✅ APScheduler импортирован")
except Exception as e:
    print(f"❌ Ошибка импорта APScheduler: {e}")
    BackgroundScheduler = None

app = Flask(__name__)
DATA_FILE = 'planner_data.json'

# Читаем токены из переменных окружения
TG_TOKEN = os.getenv('TG_TOKEN', '')
TG_CHAT = os.getenv('TG_CHAT', '')

print(f"🔑 TG_TOKEN: {'✅ есть' if TG_TOKEN else '❌ НЕТ'}")
print(f"🔑 TG_CHAT: {'✅ есть' if TG_CHAT else '❌ НЕТ'}")

def load_data():
    try:
        if not os.path.exists(DATA_FILE):
            return {'tasks':[], 'settings':{'tgToken':TG_TOKEN, 'tgChat':TG_CHAT}}
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f'❌ Ошибка загрузки данных: {e}')
        return {'tasks':[], 'settings':{'tgToken':TG_TOKEN, 'tgChat':TG_CHAT}}

def save_data(d):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'❌ Ошибка сохранения: {e}')

def send_tg(text):
    if not TG_TOKEN or not TG_CHAT:
        print('❌ TG не настроен (TG_TOKEN или TG_CHAT пустые)')
        return False
    try:
        print(f'📤 Отправляю в TG: {text[:50]}...')
        r = requests.post(
            f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage',
            json={'chat_id': TG_CHAT, 'text': text},
            timeout=10
        )
        print(f'✅ TG отправлено: {r.status_code}')
        return r.ok
    except Exception as e:
        print(f'❌ TG ошибка: {e}')
        return False

def morning_briefing():
    print('🌅 Утренний брифинг запущен')
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
        print(f'❌ Ошибка morning_briefing: {e}')

def evening_report():
    print('🌙 Вечерний отчёт запущен')
    try:
        d = load_data()
        today = datetime.now().strftime('%Y-%m-%d')
        done = [t for t in d.get('tasks',[]) if t.get('done') and t.get('doneAt') == today]
        send_tg(f"🌙 Итоги дня\n\n✅ Выполнено: {len(done)} задач")
    except Exception as e:
        print(f'❌ Ошибка evening_report: {e}')

def deadline_check():
    print('⏰ Проверка дедлайнов запущена')
    try:
        d = load_data()
        today = datetime.now().strftime('%Y-%m-%d')
        for t in d.get('tasks',[]):
            if t.get('done'): continue
            dl = t.get('deadline','')
            if dl == today:
                send_tg(f"⏰ Сегодня сдать: {t['title']}")
            elif dl < today:
                send_tg(f"🚨 Просрочено: {t['title']} (было {dl})")
    except Exception as e:
        print(f'❌ Ошибка deadline_check: {e}')

# Планировщик
if BackgroundScheduler:
    try:
        print('🔄 Запускаю APScheduler...')
        scheduler = BackgroundScheduler()
        scheduler.add_job(morning_briefing, 'cron', hour=8, minute=0)
        scheduler.add_job(evening_report, 'cron', hour=21, minute=0)
        scheduler.add_job(deadline_check, 'cron', hour=9, minute=0)
        scheduler.start()
        print('✅ Планировщик запущен успешно!')
    except Exception as e:
        print(f'❌ Ошибка запуска планировщика: {e}')
        import traceback
        traceback.print_exc()
else:
    print('⚠️ APScheduler недоступен, уведомления не будут работать')

# API для синхронизации с браузером
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

print('✅ Flask приложение настроено')

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f'🌿 Сервер запущен на порту {port}')
    print('=' * 50)
    app.run(host='0.0.0.0', port=port, debug=False)
