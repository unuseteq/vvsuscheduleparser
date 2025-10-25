import requests
from bs4 import BeautifulSoup
import telebot
import time
import schedule
from datetime import datetime, timedelta
import logging
import json
import os
from urllib.parse import urljoin
import re

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "7740456708:AAGtqjk2XcttR2iXgRfxYed0jQcNttPhDf0"
ADMIN_CHAT_ID = "8196566107"
WEBSITE_URL = "https://cabinet.vvsu.ru/time-table/"
LOGIN_URL = "https://cabinet.vvsu.ru/sign-in"
USERNAME = "" #Ваш логин
PASSWORD = "" #Ваш пароль

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Расписание пар с номерами и временем
LESSON_SCHEDULE = {
    1: {"start": "08:30", "end": "10:00", "break": "10 минут"},
    2: {"start": "10:10", "end": "11:40", "break": "10 минут"},
    3: {"start": "11:50", "end": "13:20", "break": "30 минут"},
    4: {"start": "13:50", "end": "15:20", "break": "10 минут"},
    5: {"start": "15:30", "end": "17:00", "break": "10 минут"},
    6: {"start": "17:10", "end": "18:40", "break": "10 минут"},
    7: {"start": "18:50", "end": "20:20", "break": "10 минут"}
}

class UserManager:
    def __init__(self):
        self.users_file = "allowed_users.json"
        self.allowed_users = self._load_users()
    
    def _load_users(self):
        """Загружает список разрешенных пользователей"""
        try:
            if os.path.exists(self.users_file):
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки пользователей: {e}")
        return {}
    
    def _save_users(self):
        """Сохраняет список пользователей"""
        try:
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(self.allowed_users, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения пользователей: {e}")
    
    def is_user_allowed(self, user_id):
        """Проверяет, разрешен ли пользователь"""
        return str(user_id) in self.allowed_users and self.allowed_users[str(user_id)].get('allowed', False)
    
    def has_accepted_privacy(self, user_id):
        """Проверяет, принял ли пользователь политику конфиденциальности"""
        return str(user_id) in self.allowed_users and self.allowed_users[str(user_id)].get('privacy_accepted', False)
    
    def accept_privacy_policy(self, user_id):
        """Устанавливает флаг принятия политики конфиденциальности"""
        user_id = str(user_id)
        if user_id in self.allowed_users:
            self.allowed_users[user_id]['privacy_accepted'] = True
            self.allowed_users[user_id]['privacy_accepted_time'] = datetime.now().isoformat()
            self._save_users()
            return True
        return False
    
    def add_user_request(self, user_id, username, first_name, last_name):
        """Добавляет запрос на доступ"""
        user_id = str(user_id)
        if user_id not in self.allowed_users:
            self.allowed_users[user_id] = {
                'username': username,
                'first_name': first_name,
                'last_name': last_name,
                'allowed': False,
                'privacy_accepted': False,
                'request_time': datetime.now().isoformat(),
                'last_activity': datetime.now().isoformat(),
                'command_count': 0
            }
            self._save_users()
            return True
        return False
    
    def allow_user(self, user_id):
        """Разрешает доступ пользователю"""
        user_id = str(user_id)
        if user_id in self.allowed_users:
            self.allowed_users[user_id]['allowed'] = True
            self.allowed_users[user_id]['allowed_time'] = datetime.now().isoformat()
            self._save_users()
            return True
        return False
    
    def deny_user(self, user_id):
        """Запрещает доступ пользователю"""
        user_id = str(user_id)
        if user_id in self.allowed_users:
            self.allowed_users[user_id]['allowed'] = False
            self._save_users()
            return True
        return False
    
    def get_pending_requests(self):
        """Возвращает список ожидающих запросов"""
        return {uid: data for uid, data in self.allowed_users.items() 
                if not data.get('allowed', False)}
    
    def update_user_activity(self, user_id):
        """Обновляет время последней активности пользователя"""
        user_id = str(user_id)
        if user_id in self.allowed_users:
            self.allowed_users[user_id]['last_activity'] = datetime.now().isoformat()
            self.allowed_users[user_id]['command_count'] = self.allowed_users[user_id].get('command_count', 0) + 1
            self._save_users()
    
    def get_statistics(self):
        """Возвращает статистику пользователей"""
        total_users = len(self.allowed_users)
        
        # Пользователи с доступом
        allowed_users = [uid for uid, data in self.allowed_users.items() 
                        if data.get('allowed', False)]
        
        # Пользователи, принявшие политику
        privacy_accepted = [uid for uid, data in self.allowed_users.items() 
                           if data.get('privacy_accepted', False)]
        
        # Ожидающие подтверждения
        pending_requests = [uid for uid, data in self.allowed_users.items() 
                           if not data.get('allowed', False) and data.get('privacy_accepted', False)]
        
        # Активные пользователи (активность за последние 7 дней)
        week_ago = datetime.now() - timedelta(days=7)
        active_users = []
        total_commands = 0
        
        for uid, data in self.allowed_users.items():
            total_commands += data.get('command_count', 0)
            last_activity = data.get('last_activity')
            if last_activity:
                try:
                    activity_time = datetime.fromisoformat(last_activity)
                    if activity_time >= week_ago:
                        active_users.append(uid)
                except:
                    pass
        
        # Дата первого пользователя
        first_user_date = None
        for uid, data in self.allowed_users.items():
            request_time = data.get('request_time')
            if request_time:
                try:
                    user_date = datetime.fromisoformat(request_time)
                    if not first_user_date or user_date < first_user_date:
                        first_user_date = user_date
                except:
                    pass
        
        return {
            "total_users": total_users,
            "allowed_users": len(allowed_users),
            "privacy_accepted": len(privacy_accepted),
            "pending_requests": len(pending_requests),
            "active_users_7d": len(active_users),
            "total_commands": total_commands,
            "first_user_date": first_user_date.isoformat() if first_user_date else "Неизвестно",
            "last_update": datetime.now().isoformat()
        }

# Создаем менеджер пользователей
user_manager = UserManager()

class VVGUScheduleParser:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
        })
        self.is_authenticated = False
        self.cookie_file = "vvgu_cookies.json"

    def login(self):
        """Авторизация на сайте ВВГУ с обработкой OAuth"""
        try:
            logger.info("🔐 Начало авторизации на cabinet.vvsu.ru...")
            
            # Удаляем старые куки при новой авторизации
            if os.path.exists(self.cookie_file):
                os.remove(self.cookie_file)
                logger.info("🗑️ Удалены старые куки")
            
            # 1. Получаем страницу логина
            login_page = self.session.get(LOGIN_URL)
            login_page.raise_for_status()
            
            soup = BeautifulSoup(login_page.content, 'html.parser')
            logger.info(f"📄 Страница логина получена, статус: {login_page.status_code}")
            
            # 2. Ищем форму входа для студентов
            student_form = None
            forms = soup.find_all('form')
            
            for form in forms:
                form_text = form.get_text().lower()
                if any(word in form_text for word in ['студент', 'сотрудник', 'student', 'login']):
                    student_form = form
                    break
            
            if not student_form:
                # Если не нашли по тексту, берем первую форму
                student_form = forms[0] if forms else None
            
            if not student_form:
                logger.error("❌ Форма входа не найдена")
                return False

            # 3. Ищем все поля формы
            hidden_inputs = student_form.find_all('input', type='hidden')
            login_data = {}
            
            for hidden in hidden_inputs:
                name = hidden.get('name')
                value = hidden.get('value', '')
                if name:
                    login_data[name] = value
                    logger.info(f"🔍 Найдено скрытое поле: {name} = {value[:20]}...")
            
            # 4. Добавляем логин и пароль
            login_data['login'] = USERNAME
            login_data['password'] = PASSWORD
            
            logger.info(f"📦 Данные для отправки: {list(login_data.keys())}")
            
            # 5. Определяем URL для отправки формы
            action_url = student_form.get('action', '')
            if action_url:
                action_url = urljoin(LOGIN_URL, action_url)
            else:
                action_url = LOGIN_URL
            
            logger.info(f"🎯 URL отправки формы: {action_url}")
            
            # 6. Отправляем запрос на авторизацию
            headers = {
                'Referer': LOGIN_URL,
                'Origin': 'https://cabinet.vvsu.ru',
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            
            logger.info("🚀 Отправка данных для авторизации...")
            response = self.session.post(action_url, data=login_data, headers=headers, allow_redirects=False)
            
            logger.info(f"📡 Ответ получен, статус: {response.status_code}")
            
            # Обрабатываем редиректы вручную
            if response.status_code in [301, 302, 303]:
                redirect_url = response.headers.get('Location')
                logger.info(f"🔄 Редирект на: {redirect_url}")
                if redirect_url:
                    response = self.session.get(redirect_url, allow_redirects=True)
            
            logger.info(f"🔗 Конечный URL: {response.url}")
            
            # 7. Обрабатываем OAuth редирект на fort.vvsu.ru
            if 'fort.vvsu.ru' in response.url:
                logger.info("🔄 Обнаружен OAuth редирект, обработка...")
                return self._handle_oauth_redirect(response)
            
            # 8. Проверяем успешность авторизации
            return self._check_auth_success(response)
                
        except Exception as e:
            logger.error(f"❌ Ошибка при авторизации: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _handle_oauth_redirect(self, response):
        """Обрабатывает OAuth редирект на fort.vvsu.ru"""
        try:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Ищем форму на странице fort.vvsu.ru
            form = soup.find('form')
            if not form:
                logger.error("❌ Форма OAuth не найдена")
                return False
            
            # Собираем данные формы
            oauth_data = {}
            hidden_inputs = form.find_all('input', type='hidden')
            
            for hidden in hidden_inputs:
                name = hidden.get('name')
                value = hidden.get('value', '')
                if name:
                    oauth_data[name] = value
            
            # Добавляем логин и пароль
            oauth_data['login'] = USERNAME
            oauth_data['password'] = PASSWORD
            
            logger.info(f"🎯 OAuth данные: {list(oauth_data.keys())}")
            
            # URL для отправки OAuth формы
            oauth_url = form.get('action', '')
            if not oauth_url.startswith('http'):
                oauth_url = urljoin(response.url, oauth_url)
            
            logger.info(f"🎯 OAuth URL: {oauth_url}")
            
            # Отправляем OAuth запрос с отключенным авторедиректом
            headers = {
                'Referer': response.url,
                'Origin': 'https://fort.vvsu.ru',
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            
            oauth_response = self.session.post(oauth_url, data=oauth_data, headers=headers, allow_redirects=False)
            logger.info(f"📡 OAuth ответ, статус: {oauth_response.status_code}")
            
            # Обрабатываем редиректы вручную
            if oauth_response.status_code in [301, 302, 303]:
                redirect_url = oauth_response.headers.get('Location')
                logger.info(f"🔄 OAuth редирект на: {redirect_url}")
                if redirect_url:
                    # Переходим по редиректу и сохраняем куки
                    final_response = self.session.get(redirect_url, allow_redirects=True)
                    logger.info(f"🔗 Конечный URL после OAuth: {final_response.url}")
                    
                    # После OAuth явно переходим на страницу расписания
                    schedule_response = self.session.get(WEBSITE_URL)
                    return self._check_auth_success(schedule_response)
            
            return self._check_auth_success(oauth_response)
            
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке OAuth: {e}")
            return False

    def _check_auth_success(self, response):
        """Проверяет успешность авторизации"""
        # Проверяем, что мы не на странице логина
        if 'login' in response.url.lower() or 'sign-in' in response.url.lower():
            logger.error("❌ Авторизация не удалась - остались на странице логина")
            return False
        
        # Проверяем доступ к странице расписания
        logger.info("🔄 Проверка доступа к расписанию...")
        schedule_response = self.session.get(WEBSITE_URL)
        
        success_indicators = [
            'time-table', 'timetable', 'расписание', 'schedule',
            'dashboard', 'личный кабинет', 'student', 'студент'
        ]
        
        # Проверяем по URL
        current_url = schedule_response.url.lower()
        if any(indicator in current_url for indicator in success_indicators):
            self.is_authenticated = True
            self._save_cookies()
            logger.info("✅ Успешная авторизация по URL!")
            return True
        
        # Проверяем по содержимому
        soup = BeautifulSoup(schedule_response.content, 'html.parser')
        page_text = soup.get_text().lower()
        
        if any(indicator in page_text for indicator in success_indicators):
            self.is_authenticated = True
            self._save_cookies()
            logger.info("✅ Успешная авторизация по содержимому!")
            return True
        
        logger.error("❌ Авторизация не удалась - не найдены признаки успешной авторизации")
        logger.info(f"🔍 Текущий URL: {schedule_response.url}")
        return False

    def _save_cookies(self):
        """Сохраняет куки в файл"""
        try:
            cookies_dict = requests.utils.dict_from_cookiejar(self.session.cookies)
            with open(self.cookie_file, 'w') as f:
                json.dump(cookies_dict, f)
            logger.info("✅ Куки сохранены")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения куки: {e}")

    def _load_cookies(self):
        """Загружает куки из файла"""
        try:
            if os.path.exists(self.cookie_file):
                with open(self.cookie_file, 'r') as f:
                    cookies_dict = json.load(f)
                self.session.cookies = requests.utils.cookiejar_from_dict(cookies_dict)
                logger.info("✅ Куки загружены")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки куки: {e}")
        return False

    def ensure_auth(self):
        """Проверяет и обновляет авторизацию"""
        # Всегда начинаем с чистой сессии при запуске
        if not self.is_authenticated:
            # Удаляем старые куки при запуске
            if os.path.exists(self.cookie_file):
                logger.info("🗑️ Удаляем старые куки при запуске")
                os.remove(self.cookie_file)
            
            return self.login()
        return True

    def parse_schedule(self):
        """Парсит расписание с авторизацией"""
        if not self.ensure_auth():
            logger.error("❌ Не удалось авторизоваться")
            return None

        try:
            logger.info("📖 Получение страницы расписания...")
            response = self.session.get(WEBSITE_URL)
            response.raise_for_status()
            
            # Проверяем редирект на страницу логина
            if 'sign-in' in response.url or 'login' in response.url:
                logger.warning("⚠️ Сессия устарела, повторная авторизация")
                self.is_authenticated = False
                if not self.login():
                    return None
                response = self.session.get(WEBSITE_URL)
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Проверяем, что мы на правильной странице
            page_text = soup.get_text().lower()
            if 'расписание' not in page_text and 'timetable' not in page_text:
                logger.error("❌ Не удалось найти страницу расписания")
                logger.info(f"🔍 Текущий URL: {response.url}")
                return None
            
            schedule_data = self._extract_schedule_data(soup)
            return schedule_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка при парсинге: {e}")
            return None

    def _extract_schedule_data(self, soup):
        """Извлекает данные расписания на следующий день"""
        schedule_data = []
        
        logger.info("🔍 Поиск элементов расписания...")
        
        # Определяем дату следующего дня
        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow_date_str = tomorrow.strftime("%d.%m.%Y")
        tomorrow_weekday = self._get_weekday_name(tomorrow.weekday())
        
        logger.info(f"📅 Завтрашняя дата: {tomorrow_weekday} {tomorrow_date_str}")
        
        # Поиск таблиц с расписанием
        tables = soup.find_all('table')
        logger.info(f"📊 Найдено таблиц: {len(tables)}")
        
        current_date = ""
        day_schedule = []
        found_tomorrow = False
        
        for i, table in enumerate(tables):
            if found_tomorrow:
                break
                
            logger.info(f"🔎 Анализ таблицы {i+1}...")
            rows = table.find_all('tr')
            
            for j, row in enumerate(rows):
                if not row.get_text().strip():
                    continue
                    
                cells = row.find_all(['td', 'th'])
                cell_texts = [cell.get_text(" ", strip=True) for cell in cells if cell.get_text(strip=True)]
                
                # Проверяем на заголовок с датой
                if len(cell_texts) == 1 and any(day in cell_texts[0].lower() for day in 
                    ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']):
                    current_date = cell_texts[0]
                    
                    # Проверяем, относится ли эта дата к следующему дню
                    if self._is_date_tomorrow(current_date, tomorrow_date_str, tomorrow_weekday):
                        logger.info(f"📅 Найдена дата следующего дня: {current_date}")
                        found_tomorrow = True
                    else:
                        current_date = ""
                    continue
                
                # Обрабатываем строки с расписанием только для следующего дня
                if len(cell_texts) >= 3 and current_date and found_tomorrow:
                    time_text = cell_texts[0]
                    discipline_text = cell_texts[1] if len(cell_texts) > 1 else ""
                    teacher_text = cell_texts[2] if len(cell_texts) > 2 else ""
                    lesson_type = cell_texts[3] if len(cell_texts) > 3 else ""
                    room_text = cell_texts[4] if len(cell_texts) > 4 else ""
                    
                    # Пропускаем заголовки
                    if any(word in discipline_text.lower() for word in ['дисциплина', 'предмет', 'название']):
                        continue
                    
                    # Проверяем, что это действительно занятие
                    if (time_text and discipline_text and 
                        ':' in time_text and len(discipline_text) > 3):
                        
                        # Определяем номер пары по времени
                        lesson_number = self._get_lesson_number(time_text)
                        
                        entry_parts = []
                        entry_parts.append(f"🔹 {lesson_number} пара ({time_text})")
                        entry_parts.append(f"📖 {discipline_text}")
                        
                        if teacher_text and teacher_text != discipline_text:
                            entry_parts.append(f"👤 {teacher_text}")
                        if lesson_type:
                            type_emoji = self._get_lesson_type_emoji(lesson_type)
                            entry_parts.append(f"{type_emoji} {lesson_type}")
                        if room_text:
                            entry_parts.append(f"🏫 {room_text}")
                        
                        entry = "\n".join(entry_parts)
                        day_schedule.append((lesson_number, entry))
        
        # Сортируем занятия по номеру пары и форматируем
        schedule_data = self._format_day_schedule(day_schedule, tomorrow_weekday, tomorrow_date_str)
        logger.info(f"✅ Найдено занятий на следующий день: {len(day_schedule)}")
        
        return schedule_data

    def _get_lesson_number(self, time_text):
        """Определяет номер пары по времени"""
        try:
            # Извлекаем время начала
            start_time_str = time_text.split('-')[0].strip()
            
            # Сравниваем с расписанием пар
            for lesson_num, lesson_info in LESSON_SCHEDULE.items():
                if start_time_str == lesson_info["start"]:
                    return lesson_num
            
            # Если не нашли точное совпадение, определяем по ближайшему времени
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
            
            for lesson_num, lesson_info in LESSON_SCHEDULE.items():
                lesson_start = datetime.strptime(lesson_info["start"], "%H:%M").time()
                if start_time == lesson_start:
                    return lesson_num
            
            # Если не нашли, возвращаем общее время
            return f"({start_time_str})"
            
        except Exception as e:
            logger.error(f"❌ Ошибка определения номера пары: {e}")
            return "?"

    def _get_weekday_name(self, weekday_num):
        """Возвращает название дня недели на русском"""
        weekdays = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
        return weekdays[weekday_num]

    def _is_date_tomorrow(self, date_string, tomorrow_date_str, tomorrow_weekday):
        """Проверяет, относится ли дата к следующему дню"""
        if tomorrow_weekday.lower() in date_string.lower():
            return True
        
        date_match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})', date_string)
        if date_match:
            date_str = date_match.group(1)
            return date_str == tomorrow_date_str
        
        return False

    def _get_lesson_type_emoji(self, lesson_type):
        """Возвращает эмодзи для типа занятия"""
        lesson_type = lesson_type.lower()
        if 'лекция' in lesson_type:
            return '🎓'
        elif 'практика' in lesson_type:
            return '💻'
        elif 'семинар' in lesson_type:
            return '📝'
        elif 'лабораторная' in lesson_type:
            return '🔬'
        else:
            return '📚'

    def _format_day_schedule(self, day_schedule, weekday, date_str):
        """Форматирует расписание на следующий день"""
        schedule_data = []
        
        if not day_schedule:
            schedule_data.append(f"📭 На {weekday} ({date_str}) занятий не найдено")
            return schedule_data
        
        # Заголовок дня (только один раз)
        schedule_data.append(f"📅 {weekday.capitalize()} {date_str}")
        schedule_data.append("")
        
        # Сортируем занятия по номеру пары
        day_schedule.sort(key=lambda x: x[0])
        
        # Добавляем занятия с разделителями
        for i, (lesson_num, entry) in enumerate(day_schedule):
            schedule_data.append(entry)
            if i < len(day_schedule) - 1:
                schedule_data.append("")  # Пустая строка между занятиями
        
        return schedule_data

    def format_message(self, schedule_data):
        """Форматирует сообщение (только один раз)"""
        if not schedule_data or (len(schedule_data) == 1 and "не найдено" in schedule_data[0]):
            tomorrow = datetime.now() + timedelta(days=1)
            tomorrow_str = tomorrow.strftime("%d.%m.%Y")
            weekday = self._get_weekday_name(tomorrow.weekday())
            
            return (
                f"📭 <b>Расписание ВВГУ на завтра</b>\n\n"
                f"На {weekday} ({tomorrow_str}) занятий не найдено.\n\n"
                f"🔄 Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                f"📱 Используйте /schedule для обновления"
            )
        
        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%d.%m.%Y")
        weekday = self._get_weekday_name(tomorrow.weekday())
        
        message = f"🎓 <b>ВВГУ - Расписание на завтра</b>\n"
        message += f"📆 {weekday.capitalize()} {tomorrow_str}\n\n"
        message += "\n".join(schedule_data)
        message += f"\n\n🔄 Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        message += f"\n📱 Используйте /schedule для обновления"
        
        return message

# Создаем парсер
parser = VVGUScheduleParser()

def create_privacy_keyboard():
    """Создает клавиатуру для принятия политики конфиденциальности"""
    keyboard = [
        [telebot.types.InlineKeyboardButton("✅ Принять", callback_data="accept_privacy")],
        [telebot.types.InlineKeyboardButton("❌ Отклонить", callback_data="reject_privacy")]
    ]
    return telebot.types.InlineKeyboardMarkup(keyboard)

def send_schedule_to_user(chat_id):
    """Отправляет расписание пользователю"""
    # Проверяем, принял ли пользователь политику конфиденциальности
    if not user_manager.has_accepted_privacy(chat_id):
        bot.send_message(chat_id, 
                        "❌ Сначала необходимо принять политику конфиденциальности через команду /start",
                        parse_mode='HTML')
        return False
    
    schedule_data = parser.parse_schedule()
    message = parser.format_message(schedule_data)
    
    try:
        if isinstance(message, list):
            for part in message:
                bot.send_message(chat_id, part, parse_mode='HTML')
                time.sleep(1)
        else:
            bot.send_message(chat_id, message, parse_mode='HTML')
        logger.info(f"✅ Расписание отправлено пользователю {chat_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка отправки пользователю {chat_id}: {e}")
        return False

# Команды для бота
@bot.message_handler(commands=['start', 'help'])
def start_command(message):
    user_id = str(message.from_user.id)
    user_manager.update_user_activity(user_id)
    
    # Проверяем, принял ли пользователь политику конфиденциальности
    if user_manager.has_accepted_privacy(user_id):
        # Если уже принял, показываем главное меню
        if user_manager.is_user_allowed(user_id):
            welcome_text = (
                "🎓 <b>Бот расписания ВВГУ</b>\n\n"
                "Доступ разрешен! Я помогу вам следить за расписанием занятий!\n\n"
                "<b>Доступные команды:</b>\n"
                "/schedule - 📅 Получить расписание на завтра\n"
                "/status - 🔍 Статус доступа\n"
                "/stats - 📊 Статистика бота\n"
                "/help - ❓ Помощь\n\n"
                "📱 Расписание автоматически отправляется каждый день в 12:00"
            )
            bot.send_message(message.chat.id, welcome_text, parse_mode='HTML')
        else:
            # Пользователь принял политику, но не имеет доступа
            user_data = user_manager.allowed_users.get(user_id, {})
            if user_data:
                response_text = (
                    "⏳ <b>Запрос на рассмотрении</b>\n\n"
                    "Вы приняли политику конфиденциальности.\n"
                    "Ваш запрос на доступ ожидает подтверждения администратором."
                )
            else:
                # Запрашиваем доступ
                is_new_request = user_manager.add_user_request(
                    user_id=user_id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name,
                    last_name=message.from_user.last_name
                )
                
                if is_new_request:
                    # Отправляем уведомление администратору
                    user_info = f"👤 <b>Новый запрос на доступ</b>\n\n"
                    user_info += f"ID: {user_id}\n"
                    user_info += f"Username: @{message.from_user.username or 'нет'}\n"
                    user_info += f"Имя: {message.from_user.first_name or ''}\n"
                    user_info += f"Фамилия: {message.from_user.last_name or ''}\n"
                    user_info += f"Политика конфиденциальности: ✅ Принята\n"
                    user_info += f"Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                    user_info += f"Разрешить: /allow_{user_id}\n"
                    user_info += f"Запретить: /deny_{user_id}"
                    
                    bot.send_message(ADMIN_CHAT_ID, user_info, parse_mode='HTML')
                    
                    response_text = (
                        "🔐 <b>Доступ к боту ограничен</b>\n\n"
                        "Вы приняли политику конфиденциальности.\n"
                        "Ваш запрос на доступ отправлен администратору.\n"
                        "Ожидайте подтверждения.\n\n"
                        "Вы получите уведомление, когда доступ будет предоставлен."
                    )
                else:
                    response_text = (
                        "⏳ <b>Запрос на рассмотрении</b>\n\n"
                        "Вы приняли политику конфиденциальности.\n"
                        "Ваш запрос уже отправлен администратору.\n"
                        "Ожидайте подтверждения доступа."
                    )
            
            bot.send_message(message.chat.id, response_text, parse_mode='HTML')
    else:
        # Показываем политику конфиденциальности
        privacy_text = (
            "📋 <b>Политика конфиденциальности</b>\n\n"
            "Перед использованием бота, пожалуйста, ознакомьтесь с нашей политикой конфиденциальности:\n"
            "https://telegra.ph/Politika-konfidencialnosti-10-20-55\n\n"
            "Для продолжения работы с ботом необходимо принять политику конфиденциальности."
        )
        
        reply_markup = create_privacy_keyboard()
        bot.send_message(message.chat.id, privacy_text, reply_markup=reply_markup, parse_mode='HTML')

# Обработчик callback'ов для кнопок политики конфиденциальности
@bot.callback_query_handler(func=lambda call: call.data in ['accept_privacy', 'reject_privacy'])
def handle_privacy_callback(call):
    user_id = str(call.from_user.id)
    user_manager.update_user_activity(user_id)
    
    if call.data == 'accept_privacy':
        # Пользователь принимает политику
        user_manager.accept_privacy_policy(user_id)
        
        # Добавляем запрос на доступ, если его еще нет
        if user_id not in user_manager.allowed_users:
            user_manager.add_user_request(
                user_id=user_id,
                username=call.from_user.username,
                first_name=call.from_user.first_name,
                last_name=call.from_user.last_name
            )
        
        # Уведомляем администратора
        user_info = f"👤 <b>Пользователь принял политику конфиденциальности</b>\n\n"
        user_info += f"ID: {user_id}\n"
        user_info += f"Username: @{call.from_user.username or 'нет'}\n"
        user_info += f"Имя: {call.from_user.first_name or ''}\n"
        user_info += f"Фамилия: {call.from_user.last_name or ''}\n"
        user_info += f"Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        user_info += f"Разрешить: /allow_{user_id}\n"
        user_info += f"Запретить: /deny_{user_id}"
        
        bot.send_message(ADMIN_CHAT_ID, user_info, parse_mode='HTML')
        
        # Сообщение пользователю
        response_text = (
            "✅ <b>Политика конфиденциальности принята!</b>\n\n"
            "Ваш запрос на доступ отправлен администратору.\n"
            "Ожидайте подтверждения доступа к функциям бота.\n\n"
            "Вы получите уведомление, когда доступ будет предоставлен."
        )
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=response_text,
            parse_mode='HTML'
        )
        
    else:
        # Пользователь отклоняет политику
        response_text = (
            "❌ <b>Политика конфиденциальности отклонена</b>\n\n"
            "Для использования бота необходимо принять политику конфиденциальности.\n\n"
            "Если вы передумаете, используйте команду /start снова."
        )
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=response_text,
            parse_mode='HTML'
        )

@bot.message_handler(commands=['schedule'])
def schedule_command(message):
    user_id = str(message.from_user.id)
    user_manager.update_user_activity(user_id)
    
    # Проверяем, принял ли пользователь политику конфиденциальности
    if not user_manager.has_accepted_privacy(user_id):
        bot.send_message(message.chat.id, 
                        "❌ <b>Сначала необходимо принять политику конфиденциальности</b>\n\n"
                        "Используйте /start для просмотра и принятия политики.", 
                        parse_mode='HTML')
        return
    
    if user_manager.is_user_allowed(user_id):
        bot.send_message(message.chat.id, "🔄 Получаю актуальное расписание на завтра...")
        send_schedule_to_user(message.chat.id)
    else:
        bot.send_message(message.chat.id, 
                        "❌ <b>Доступ запрещен</b>\n\n"
                        "Ваш запрос на доступ ожидает подтверждения администратором.\n"
                        "Используйте /status для проверки статуса.", 
                        parse_mode='HTML')

@bot.message_handler(commands=['status'])
def status_command(message):
    user_id = str(message.from_user.id)
    user_manager.update_user_activity(user_id)
    
    if not user_manager.has_accepted_privacy(user_id):
        status_text = (
            "❌ <b>Статус: Политика конфиденциальности не принята</b>\n\n"
            "Используйте /start для просмотра и принятия политики конфиденциальности."
        )
    elif user_manager.is_user_allowed(user_id):
        status_text = "✅ <b>Статус: Доступ разрешен</b>\n\nВы можете использовать все функции бота."
    else:
        user_data = user_manager.allowed_users.get(user_id, {})
        if user_data:
            status_text = (
                "⏳ <b>Статус: Ожидание подтверждения</b>\n\n"
                "Вы приняли политику конфиденциальности.\n"
                "Ваш запрос на доступ ожидает подтверждения администратором."
            )
        else:
            status_text = (
                "❌ <b>Статус: Доступ запрещен</b>\n\n"
                "Используйте /start для запроса доступа к боту."
            )
    
    bot.send_message(message.chat.id, status_text, parse_mode='HTML')

@bot.message_handler(commands=['stats'])
def stats_command(message):
    user_id = str(message.from_user.id)
    user_manager.update_user_activity(user_id)
    
    # Проверяем права администратора
    if user_id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ У вас нет прав для просмотра статистики")
        return
    
    stats = user_manager.get_statistics()
    
    # Форматируем дату первого пользователя
    first_date = "Неизвестно"
    if stats["first_user_date"] != "Неизвестно":
        try:
            first_date_obj = datetime.fromisoformat(stats["first_user_date"])
            first_date = first_date_obj.strftime("%d.%m.%Y %H:%M")
        except:
            first_date = "Неизвестно"
    
    stats_text = (
        "📊 <b>Статистика бота ВВГУ</b>\n\n"
        f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
        f"✅ Пользователей с доступом: <b>{stats['allowed_users']}</b>\n"
        f"📋 Приняли политику: <b>{stats['privacy_accepted']}</b>\n"
        f"⏳ Ожидают подтверждения: <b>{stats['pending_requests']}</b>\n"
        f"📈 Активных за 7 дней: <b>{stats['active_users_7d']}</b>\n"
        f"🔄 Всего команд: <b>{stats['total_commands']}</b>\n"
        f"📅 Первый пользователь: <b>{first_date}</b>\n"
        f"🕒 Последнее обновление: <b>{datetime.now().strftime('%d.%m.%Y %H:%M')}</b>"
    )
    
    bot.send_message(message.chat.id, stats_text, parse_mode='HTML')

# Админские команды
@bot.message_handler(commands=['admin'])
def admin_command(message):
    user_id = str(message.from_user.id)
    user_manager.update_user_activity(user_id)
    
    if user_id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ У вас нет прав администратора")
        return
    
    pending_requests = user_manager.get_pending_requests()
    
    if not pending_requests:
        bot.send_message(message.chat.id, "✅ Нет ожидающих запросов на доступ")
        return
    
    response = f"⏳ <b>Ожидающие запросы ({len(pending_requests)}):</b>\n\n"
    
    for uid, data in pending_requests.items():
        response += f"👤 {data.get('first_name', '')} {data.get('last_name', '')}\n"
        response += f"📱 @{data.get('username', 'нет')}\n"
        response += f"🆔 {uid}\n"
        response += f"⏰ {data.get('request_time', 'неизвестно')}\n"
        response += f"Разрешить: /allow_{uid}\n"
        response += f"Запретить: /deny_{uid}\n\n"
    
    bot.send_message(message.chat.id, response, parse_mode='HTML')

@bot.message_handler(regexp=r"^/allow_\d+$")
def allow_user_command(message):
    user_id = str(message.from_user.id)
    user_manager.update_user_activity(user_id)
    
    if user_id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ У вас нет прав администратора")
        return
    
    target_user_id = message.text.split('_')[1]
    
    if user_manager.allow_user(target_user_id):
        # Уведомляем пользователя
        try:
            bot.send_message(target_user_id, 
                           "✅ <b>Доступ разрешен!</b>\n\n"
                           "Теперь вы можете использовать все функции бота!\n"
                           "Используйте /schedule для получения расписания.", 
                           parse_mode='HTML')
        except Exception as e:
            logger.error(f"❌ Не удалось уведомить пользователя {target_user_id}: {e}")
        
        bot.send_message(message.chat.id, f"✅ Пользователю {target_user_id} разрешен доступ")
    else:
        bot.send_message(message.chat.id, f"❌ Не удалось разрешить доступ пользователю {target_user_id}")

@bot.message_handler(regexp=r"^/deny_\d+$")
def deny_user_command(message):
    user_id = str(message.from_user.id)
    user_manager.update_user_activity(user_id)
    
    if user_id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ У вас нет прав администратора")
        return
    
    target_user_id = message.text.split('_')[1]
    
    if user_manager.deny_user(target_user_id):
        # Уведомляем пользователя
        try:
            bot.send_message(target_user_id, 
                           "❌ <b>Доступ запрещен</b>\n\n"
                           "Администратор отклонил ваш запрос на доступ к боту.", 
                           parse_mode='HTML')
        except Exception as e:
            logger.error(f"❌ Не удалось уведомить пользователя {target_user_id}: {e}")
        
        bot.send_message(message.chat.id, f"✅ Пользователю {target_user_id} запрещен доступ")
    else:
        bot.send_message(message.chat.id, f"❌ Не удалось запретить доступ пользователю {target_user_id}")

@bot.message_handler(commands=['users'])
def list_users_command(message):
    user_id = str(message.from_user.id)
    user_manager.update_user_activity(user_id)
    
    if user_id != ADMIN_CHAT_ID:
        bot.send_message(message.chat.id, "❌ У вас нет прав администратора")
        return
    
    allowed_users = {uid: data for uid, data in user_manager.allowed_users.items() 
                    if data.get('allowed', False)}
    
    if not allowed_users:
        bot.send_message(message.chat.id, "✅ Нет пользователей с доступом")
        return
    
    response = f"👥 <b>Пользователи с доступом ({len(allowed_users)}):</b>\n\n"
    
    for uid, data in allowed_users.items():
        response += f"👤 {data.get('first_name', '')} {data.get('last_name', '')}\n"
        response += f"📱 @{data.get('username', 'нет')}\n"
        response += f"🆔 {uid}\n"
        response += f"✅ Доступ разрешен: {data.get('allowed_time', 'неизвестно')}\n"
        response += f"📋 Политика принята: {'✅' if data.get('privacy_accepted') else '❌'}\n"
        response += f"🔄 Команд выполнено: {data.get('command_count', 0)}\n\n"
    
    bot.send_message(message.chat.id, response, parse_mode='HTML')

def send_daily_schedule():
    """Функция для отправки расписания всем пользователям в 12:00+10 UTC"""
    logger.info("🕛 Начало отправки ежедневного расписания...")
    
    # Получаем расписание
    schedule_data = parser.parse_schedule()
    if not schedule_data:
        logger.error("❌ Не удалось получить расписание для ежедневной рассылки")
        return
    
    message = parser.format_message(schedule_data)
    
    # Отправляем всем пользователям с доступом
    success_count = 0
    error_count = 0
    
    for user_id, user_data in user_manager.allowed_users.items():
        if user_data.get('allowed', False) and user_data.get('privacy_accepted', False):
            try:
                if isinstance(message, list):
                    for part in message:
                        bot.send_message(user_id, part, parse_mode='HTML')
                        time.sleep(1)
                else:
                    bot.send_message(user_id, message, parse_mode='HTML')
                success_count += 1
                logger.info(f"✅ Ежедневное расписание отправлено пользователю {user_id}")
            except Exception as e:
                error_count += 1
                logger.error(f"❌ Ошибка отправки ежедневного расписания пользователю {user_id}: {e}")
            
            # Пауза между отправками
            time.sleep(0.5)
    
    logger.info(f"📊 Ежедневная рассылка завершена: успешно {success_count}, ошибок {error_count}")

# Настройка расписания для отправки в обед (12:00+10 UTC)
def setup_scheduler():
    """Настраивает планировщик для ежедневной отправки в 12:00+10 UTC"""
    # UTC+10 соответствует 02:00 UTC
    schedule.every().day.at("02:00").do(send_daily_schedule)  # 12:00+10 UTC = 02:00 UTC
    logger.info("⏰ Планировщик настроен: ежедневная отправка в 12:00+10 UTC (02:00 UTC)")

def run_scheduler():
    """Запускает планировщик в отдельном потоке"""
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Проверяем каждую минуту
        except Exception as e:
            logger.error(f"❌ Ошибка в планировщике: {e}")
            time.sleep(60)

if __name__ == "__main__":
    try:
        logger.info("🤖 Бот запускается...")
        
        # Настраиваем планировщик
        setup_scheduler()
        
        # Запускаем планировщик в отдельном потоке
        import threading
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        
        logger.info("✅ Бот запущен и готов к работе")
        logger.info("⏰ Ежедневная отправка расписания настроена на 12:00+10 UTC")
        
        # Запускаем бота
        bot.polling(none_stop=True, timeout=60)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())