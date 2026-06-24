"""
Python-сервер для 24/7 уведомлений + почасовое распределение задач.
Railway-совместимая версия с Telegram-ботом.
"""
import json
import os
import re
import requests
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)
DATA_FILE = 'planner_data.json'

TG_TOKEN = os.getenv('TG_TOKEN', '')
TG_CHAT = os.getenv('TG_CHAT', '')

# ========== CORS ==========
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.route('/api/data', methods=['OPTIONS'])
def options_data():
    return '', 204

# ========== ДАННЫЕ ==========
def load_data():
    try:
        if not os.path.exists(DATA_FILE):
            return {
                'tasks': [],
                'settings': {
                    'tgToken': TG_TOKEN,
                    'tgChat': TG_CHAT,
                    'workStart': '08:00',
                    'workEnd': '22:00',
                    'max': 6
                }
            }
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f'Ошибка загрузки: {e}')
        return {'tasks': [], 'settings': {'tgToken': TG_TOKEN, 'tgChat': TG_CHAT}}

def save_data(d):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'Ошибка сохранения: {e}')

# ========== TELEGRAM ==========
def send_tg(text, chat_id=None):
    if not TG_TOKEN:
        print('TG_TOKEN не настроен')
        return False
    target_chat = chat_id or TG_CHAT
    try:
        r = requests.post(
            f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage',
            json={'chat_id': target_chat, 'text': text},
            timeout=10
        )
        print(f'TG: {r.status_code}')
        return r.ok
    except Exception as e:
        print(f'TG ошибка: {e}')
        return False

# ========== ПОЧАСОВОЕ РАСПИСАНИЕ ==========
def schedule_hourly(data, skip_breakfast=False):
    """Распределяет задачи по часам с учётом приёмов пищи"""
    today = datetime.now().strftime('%Y-%m-%d')
    work_start = data.get('settings', {}).get('workStart', '08:00')
    
    start_hour, start_min = map(int, work_start.split(':'))
    current_time = datetime.now().replace(
        hour=start_hour, minute=start_min, second=0, microsecond=0
    )
    
    # Если сейчас позже времени начала — начинаем с текущего времени
    if datetime.now() > current_time:
        current_time = datetime.now().replace(second=0, microsecond=0)
        if current_time.minute < 30:
            current_time = current_time.replace(minute=0)
        else:
            current_time = current_time.replace(minute=30)
    
    # Время приёмов пищи
    meals = {
        'breakfast': {'time': '08:30', 'duration': 30, 'skip': skip_breakfast},
        'lunch': {'time': '13:00', 'duration': 60, 'skip': False},
        'dinner': {'time': '19:00', 'duration': 45, 'skip': False}
    }
    
    # Задачи на сегодня
    tasks_today = [t for t in data.get('tasks', []) 
                   if not t.get('done') and t.get('scheduledDate') == today]
    
    # Сортируем по приоритету
    priority_order = {'high': 0, 'mid': 1, 'low': 2}
    tasks_today.sort(key=lambda t: priority_order.get(t.get('priority', 'mid'), 1))
    
    schedule = []
    task_index = 0
    
    while task_index < len(tasks_today) and current_time.hour < 22:
        # Проверяем приём пищи
        meal_time = None
        for meal_name, meal_info in meals.items():
            if meal_info['skip']:
                continue
            meal_h, meal_m = map(int, meal_info['time'].split(':'))
            meal_start = current_time.replace(hour=meal_h, minute=meal_m, second=0)
            
            if meal_start <= current_time + timedelta(minutes=15):
                meal_time = meal_name
                meal_duration = meal_info['duration']
                break
        
        if meal_time:
            schedule.append({
                'type': 'meal',
                'name': {
                    'breakfast': '🍳 Завтрак',
                    'lunch': '🥗 Обед',
                    'dinner': '🍽 Ужин'
                }[meal_time],
                'start': current_time.strftime('%H:%M'),
                'duration': meal_duration
            })
            current_time += timedelta(minutes=meal_duration)
            meals[meal_time]['skip'] = True
        else:
            task = tasks_today[task_index]
            hours = float(task.get('hours', 1))
            duration_min = int(hours * 60)
            
            schedule.append({
                'type': 'task',
                'name': task['title'],
                'start': current_time.strftime('%H:%M'),
                'duration': duration_min,
                'taskId': task['id']
            })
            
            current_time += timedelta(minutes=duration_min)
            task_index += 1
    
    return schedule

def format_schedule(schedule):
    """Форматирует расписание для Telegram"""
    if not schedule:
        return "🌿 На сегодня задач нет"
    
    msg = "📅 Расписание на сегодня:\n\n"
    for item in schedule:
        if item['type'] == 'meal':
            msg += f"{item['start']} {item['name']} ({item['duration']} мин)\n"
        else:
            hours = item['duration'] / 60
            msg += f"{item['start']} 📌 {item['name']} ({hours}ч)\n"
    
    return msg

# ========== АВТОМАТИЧЕСКИЕ НАПОМИНАНИЯ ==========
def morning_briefing():
    try:
        data = load_data()
        today = datetime.now().strftime('%Y-%m-%d')
        tasks = [t for t in data.get('tasks', []) 
                if not t.get('done') and t.get('scheduledDate') == today]
        h = sum(float(t.get('hours', 0)) for t in tasks)
        msg = f"🌿 Доброе утро!\n\nСегодня: {len(tasks)} задач • {h}ч\n\n"
        for t in tasks:
            msg += f"• {t['title']} — {t['hours']}ч\n"
        msg += "\n💡 Напиши /встала чтобы получить расписание по часам"
        send_tg(msg)
    except Exception as e:
        print(f'Ошибка: {e}')

def evening_report():
    try:
        data = load_data()
        today = datetime.now().strftime('%Y-%m-%d')
        done = [t for t in data.get('tasks', []) 
                if t.get('done') and t.get('doneAt') == today]
        send_tg(f"🌙 Итоги дня\n\n✅ Выполнено: {len(done)} задач")
    except Exception as e:
        print(f'Ошибка: {e}')

def deadline_check():
    try:
        data = load_data()
        today = datetime.now().strftime('%Y-%m-%d')
        for t in data.get('tasks', []):
            if t.get('done'):
                continue
            dl = t.get('deadline', '')
            if dl == today:
                send_tg(f"⏰ Сегодня сдать: {t['title']}")
            elif dl < today:
                send_tg(f"🚨 Просрочено: {t['title']}")
    except Exception as e:
        print(f'Ошибка: {e}')

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(morning_briefing, 'cron', hour=8, minute=0)
    scheduler.add_job(evening_report, 'cron', hour=21, minute=0)
    scheduler.add_job(deadline_check, 'cron', hour=9, minute=0)
    scheduler.start()
    print('✅ Планировщик запущен')
except Exception as e:
    print(f'Ошибка планировщика: {e}')

# ========== КОМАНДЫ БОТА ==========
def handle_command(text, chat_id):
    text_lower = text.lower().strip()
    
    if text_lower in ['/start', '/help', 'помощь']:
        send_tg(
            "🌿 Привет! Я твой планировщик.\n\n"
            "Команды:\n"
            "/встала — начать день (с завтраком)\n"
            "/без_завтрака — начать день (без завтрака)\n"
            "/расписание — показать расписание\n"
            "/задачи — список задач на сегодня\n\n"
            "Или просто напиши задачу:\n"
            "Сделать демо 3 часа до 25.06",
            chat_id
        )
        return True
    
    if text_lower in ['/встала', 'встала', 'я встала']:
        data = load_data()
        schedule = schedule_hourly(data, skip_breakfast=False)
        msg = format_schedule(schedule)
        send_tg(msg, chat_id)
        return True
    
    if text_lower in ['/без_завтрака', 'без завтрака', 'без_завтрака']:
        data = load_data()
        schedule = schedule_hourly(data, skip_breakfast=True)
        msg = format_schedule(schedule)
        send_tg(msg, chat_id)
        return True
    
    if text_lower in ['/расписание', 'расписание']:
        data = load_data()
        schedule = schedule_hourly(data, skip_breakfast=False)
        msg = format_schedule(schedule)
        send_tg(msg, chat_id)
        return True
    
    if text_lower in ['/задачи', 'задачи', '/list']:
        data = load_data()
        today = datetime.now().strftime('%Y-%m-%d')
        tasks = [t for t in data.get('tasks', []) 
                if not t.get('done') and t.get('scheduledDate') == today]
        if tasks:
            msg = '📅 Задачи на сегодня:\n\n'
            for t in tasks:
                msg += f"• {t['title']} — {t['hours']}ч\n"
            send_tg(msg, chat_id)
        else:
            send_tg('🌿 На сегодня задач нет', chat_id)
        return True
    
    return False

# ========== СОЗДАНИЕ ЗАДАЧИ ИЗ СООБЩЕНИЯ ==========
def handle_new_task(text, chat_id):
    """Создаёт новую задачу из сообщения"""
    hours_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:часа?|ч)', text, re.IGNORECASE)
    hours = float(hours_match.group(1)) if hours_match else 2.0
    
    date_match = re.search(r'до\s+(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?', text)
    if date_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year = int(date_match.group(3)) if date_match.group(3) else datetime.now().year
        if year < 100:
            year += 2000
        deadline = f"{year}-{month:02d}-{day:02d}"
    else:
        deadline = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
    
    title = re.sub(r'\d+(?:\.\d+)?\s*(?:часа?|ч)', '', text, flags=re.IGNORECASE)
    title = re.sub(r'до\s+\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?', '', title)
    title = title.strip()
    
    if not title:
        send_tg('❌ Не понял задачу. Напиши /help', chat_id)
        return
    
    data = load_data()
    task = {
        'id': f"tg_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        'title': title,
        'hours': hours,
        'deadline': deadline,
        'start': datetime.now().strftime('%Y-%m-%d'),
        'priority': 'mid',
        'projectId': 'p1',
        'created': datetime.now().strftime('%Y-%m-%d'),
        'scheduledDate': datetime.now().strftime('%Y-%m-%d'),
        'done': False,
        'movedCount': 0
    }
    data['tasks'].append(task)
    save_data(data)
    
    msg = f'✅ Задача создана!\n\n📌 {title}\n⏱ {hours} часа\n📅 Сдать: {deadline}'
    send_tg(msg, chat_id)

# ========== WEBHOOK TELEGRAM ==========
@app.route(f'/webhook/{TG_TOKEN}', methods=['POST'])
def webhook():
    try:
        update = request.json
        if 'message' in update:
            message = update['message']
            text = message.get('text', '')
            chat_id = message.get('chat', {}).get('id')
            
            if chat_id:
                if not handle_command(text, chat_id):
                    handle_new_task(text, chat_id)
        
        return jsonify({'ok': True})
    except Exception as e:
        print(f'Webhook ошибка: {e}')
        return jsonify({'ok': False}), 500

# ========== РАЗДАЧА СТАТИКИ ==========
@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

# ========== API ==========
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

@app.route('/api/schedule', methods=['GET'])
def get_schedule():
    """Возвращает расписание на сегодня"""
    data = load_data()
    skip_breakfast = request.args.get('skip_breakfast', 'false').lower() == 'true'
    schedule = schedule_hourly(data, skip_breakfast)
    return jsonify({'schedule': schedule})

@app.route('/api/send', methods=['POST'])
def manual_send():
    text = request.json.get('text', '')
    ok = send_tg(text)
    return jsonify({'ok': ok})

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f'🌿 Сервер запущен на порту {port}')
    print(f'🔑 TG_TOKEN: {"✅" if TG_TOKEN else "❌"}')
    print(f'🔑 TG_CHAT: {"✅" if TG_CHAT else "❌"}')
    app.run(host='0.0.0.0', port=port, debug=False)
