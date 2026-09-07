# -*- coding: utf-8 -*-
"""
УрФУ Столовая — сайт загруженности столовых (Этап 1).

Всё приложение в одном файле:
- данные о корпусах и позиции меток,
- HTML-страница со стилями,
- Flask-сервер и маршруты.

Запуск:  python run.py
Открыть: http://127.0.0.1:5000/
"""
import json
import os
import secrets
import threading
import time

from flask import Flask, jsonify, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash

# ===== Данные о корпусах ================================================
# Статика (имена, расположение, позиции меток) — здесь.
# «Живое» состояние загруженности (load) — в backend/data/load.json,
# чтобы его можно было менять через форму оценки без правки кода.


def _make_pins(code):
    """Словарь файлов пин-картинок для корпуса по его коду."""
    return {level: f"pin-{level}-{code}.png" for level in ("low", "medium", "high")}


# (имя, код, расположение столовой, загрузка по умолчанию, pin_x, pin_y)
_CORPS = [
    ("ИРИТ-РТФ", "irit", "2 этаж, крыло Б", "low", 46, 23),
    ("ИнЭУ",     "ineu", "1 этаж, справа от входа", "medium", 82, 13),
    ("ОЦК",      "cimt", "2 этаж, атриум", "high", 17, 70),
]

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_LOAD_FILE = os.path.join(_DATA_DIR, "load.json")
_LOCATIONS_FILE = os.path.join(_DATA_DIR, "locations.json")
_MENU_FILE = os.path.join(_DATA_DIR, "menu.json")

# Блокировка для потокобезопасной записи JSON-файлов.
_IO_LOCK = threading.Lock()

# Гарантируем, что каталог данных существует (создаётся один раз при старте).
os.makedirs(_DATA_DIR, exist_ok=True)


# Значения по умолчанию (используются как fallback, если JSON-файл отсутствует/битый).
DEFAULT_LOADS = {code: load for name, code, loc, load, x, y in _CORPS}
DEFAULT_LOCATIONS = {code: loc for name, code, loc, load, x, y in _CORPS}


def _load_json(path, defaults):
    """Читает JSON-файл, дополняя данные значениями по умолчанию. При ошибке — только defaults."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {code: data.get(code, d) for code, d in defaults.items()}
    except (OSError, ValueError):
        return defaults


def _save_json(path, data):
    """Сохраняет данные в JSON-файл (потокобезопасно и атомарно).

    Сначала пишем во временный файл в том же каталоге, затем атомарно
    переименовываем os.replace(). Если процесс падает в середине записи,
    основной файл не остаётся обрезанным/битым.
    """
    with _IO_LOCK:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


# Считываем актуальные load и расположения один раз при старте приложения.
_CURRENT_LOADS = _load_json(_LOAD_FILE, DEFAULT_LOADS)
_CURRENT_LOCATIONS = _load_json(_LOCATIONS_FILE, DEFAULT_LOCATIONS)


def _load_menu():
    """Читает меню из JSON-файла. При отсутствии/ошибке — пустое меню для всех корпусов."""
    defaults = {code: [] for name, code, loc, load, x, y in _CORPS}
    try:
        with open(_MENU_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {code: data.get(code, d) for code, d in defaults.items()}
    except (OSError, ValueError):
        return defaults


def _save_menu(menu):
    """Сохраняет меню в JSON-файл."""
    _save_json(_MENU_FILE, menu)


def _normalize_menu(menu):
    """Гарантирует корректную структуру меню: список категорий с items и id/visible/number."""
    normalized = {}
    for code in (entry[1] for entry in _CORPS):
        cats = []
        cat_index = 1
        for cat in menu.get(code, []):
            if not isinstance(cat, dict):
                continue
            cat_id = cat.get("id") or f"c{cat_index}"
            items = []
            item_index = 1
            for item in cat.get("items", []):
                if not isinstance(item, dict):
                    continue
                item_id = item.get("id") or f"{cat_id}i{item_index}"
                items.append({
                    "id": str(item_id),
                    "name": str(item.get("name", "")).strip(),
                    "price": int(item.get("price", 0) or 0),
                    "description": str(item.get("description", "")).strip(),
                    "visible": bool(item.get("visible", True)),
                })
                item_index += 1
            cats.append({
                "id": str(cat_id),
                "name": str(cat.get("name", "")).strip(),
                "visible": bool(cat.get("visible", True)),
                "items": items,
            })
            cat_index += 1
        normalized[code] = cats
    return normalized


_CURRENT_MENU = _normalize_menu(_load_menu())


def _save_menu_normalized():
    """Сохраняет нормализованное (полное) меню обратно в файл."""
    _save_menu(_CURRENT_MENU)


def corpus_by_id(corpus_id):
    """Возвращает корпус по id (коду) или None."""
    for entry in _CORPS:
        if entry[1] == corpus_id:
            return entry
    return None


def corpus_dict(entry):
    """Превращает кортеж корпуса в словарь для шаблона, с актуальными load и расположением."""
    name, code, canteen_location, default_load, x, y = entry
    return {
        "id": code,
        "name": name,
        "canteen_location": _CURRENT_LOCATIONS.get(code, canteen_location),
        "load": _CURRENT_LOADS.get(code, default_load),
        "pin_x": x,
        "pin_y": y,
        "pin_files": _make_pins(code),
    }


# Расшифровка цвета словами (используется и на главной, и на странице корпуса)
LOAD_DESCRIPTIONS = {
    "low": ("Свободно", "Можно спокойно поесть, без очереди."),
    "medium": ("Средняя загруженность", "Вероятно, придётся немного подождать."),
    "high": ("Высокая загруженность", "Большая очередь, лучше прийти позже."),
}

# Пароль администратора хранится в виде hash (не открытым текстом).
# Сам пароль не лежит в коде — проверка идёт через check_password_hash.
_ADMIN_PASSWORD_HASH = (
    "scrypt:32768:8:1$uZNopTcflQI19Gor$8073e52ac6c92ce10f64adc015d7f479835fb145"
    "6ae80ce7a5f00849854a5798d5940b63a74ad995580fd973d8011e8bfe04ccbf6aecd2c3c"
    "2453124d4862243"
)

# ===== CSRF-защита ======================================================
# Для каждой сессии генерируется токен; все мутирующие запросы (POST/PUT/
# PATCH/DELETE) проверяют его. Клиент обязан передавать токен заголовком
# X-CSRF-Token. Это блокирует cross-site request forgery с чужих сайтов.

def get_csrf_token():
    """Возвращает (и при необходимости создаёт) CSRF-токен для текущей сессии."""
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def _csrf_protect():
    """Проверяет CSRF-токен на мутирующий запрос. Возвращает None или ответ с ошибкой."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token") or ""
    token = session.get("_csrf_token")
    if not token or supplied != token:
        return jsonify({"error": "Неправильный или отсутствующий CSRF-токен"}), 403
    return None

# ===== Страница (HTML + CSS) ============================================
INDEX_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="icon" href="{{ url_for('static', filename='img/favicon.png') }}" type="image/png">
  <title>УрФУ Столовая — главная</title>
  <style>
    /* ===== Фирменные цвета ===== */
    :root {
      --color-primary: #0f1c4d;
      --color-primary-light: #1c2f78;
--color-accent: #e5b800;
      --color-bg: #e6e6e6;
      --color-text: #1a1a1a;
      --color-load-low: #2e9e4f;
      --color-load-medium: #ffbf00;
      --color-load-high: #d63333;
      --color-cream: #fbf7ee;
      --color-wine: #7c0921;
      --radius: 16px;
      --shadow: 0 4px 14px rgba(15, 28, 77, 0.12);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: system-ui, -apple-system, "Segoe UI", Arial, sans-serif;
      background: var(--color-bg);
      color: var(--color-text);
      overflow-x: hidden;
    }

    /* ===== Шапка ===== */
    .site-header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 20px 22px;
      background: var(--color-primary);
      color: #ffffff;
    }

    .brand { display: flex; align-items: center; gap: 14px; }

    .brand-logo-link { display: inline-flex; line-height: 0; }

    .brand-logo {
      width: 125px;
      height: 125px;
      border-radius: 50%;
      object-fit: cover;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
    }

    .brand-title {
      font-size: 34px;
      font-weight: 800;
      letter-spacing: 0.3px;
      margin-left: 14px;
      color: var(--color-cream);
    }

    .role-box {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 6px;
      width: 100%;
    }

    .role-label { font-size: 22px; color: #d9ddee; margin-right: 8px; }
    .role-label strong { color: #ff5252; }

    .role-prefix {
      font-size: 24px;
      font-style: italic;
      font-weight: 500;
      letter-spacing: 1px;
      color: #f4efe2;
    }

    /* Кнопка входа/выхода */
    .btn-role {
      background: var(--color-cream);
      color: var(--color-wine);
      border: 2px solid var(--color-wine);
      border-radius: 12px;
      font-size: 18px;
      font-weight: 800;
      line-height: 1.15;
      padding: 14px 22px;
      min-height: 58px;
      margin-right: -6px;
      text-align: center;
      cursor: pointer;
      box-shadow: 0 4px 10px rgba(124, 9, 33, 0.28);
      transition: transform 0.12s ease, box-shadow 0.12s ease;
    }

    .btn-role:hover {
      transform: translateY(-1px);
      box-shadow: 0 6px 14px rgba(124, 9, 33, 0.35);
    }

    .btn-role:active { transform: scale(0.96); }

    /* ===== Карта кампуса ===== */
    .map-section {
      padding: 4px 20px 20px;
      max-width: 600px;
      margin: 0 auto;
      min-height: calc(100vh - 170px);
      display: flex;
      flex-direction: column;
    }

    .map-title {
      font-size: clamp(19px, 5.2vw, 37px);
      font-weight: 900;
      width: fit-content;
      white-space: nowrap;
      margin: 4px auto 22px;
      color: #10245c;
      text-align: center;
      letter-spacing: 0.5px;
      transform: translate(-1px, -10px);
    }

    .map-title::after {
      content: "";
      display: block;
      width: calc(100% - 180px);
      margin: 6px auto 0;
      height: 5px;
      border-radius: 2px;
      background: linear-gradient(90deg, var(--color-accent), var(--color-wine));
    }

    .campus-map-wrap {
      position: relative;
      border-radius: var(--radius);
      overflow: hidden;
      box-shadow: var(--shadow);
      background: #eef1f6;
    }

    .campus-map-img { width: 100%; height: auto; display: block; }

    /* Метки загруженности */
    .map-pin {
      position: absolute;
      transform: translate(-50%, -50%);
      display: flex;
      align-items: center;
      justify-content: center;
      text-decoration: none;
      z-index: 2;
      filter: drop-shadow(0 3px 5px rgba(0, 0, 0, 0.35));
      transition: transform 0.12s ease;
    }

    .map-pin:hover { transform: translate(-50%, -50%) scale(1.06); }
    .map-pin:active { transform: translate(-50%, -50%) scale(0.96); }

    .map-pin-img {
      width: 100px;
      height: 100px;
      border-radius: 4px;
      object-fit: cover;
    }

    /* ===== Легенда цветов ===== */
    .load-legend {
      list-style: none;
      padding: 20px 26px;
      margin: 22px 0 0;
      font-size: 19px;
      background: #e2e2e2;
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }

    .load-legend li {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 9px 0;
    }

    .legend-dot {
      width: 18px;
      height: 18px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .legend-dot.dot-low    { background: var(--color-load-low); }
    .legend-dot.dot-medium { background: var(--color-load-medium); }
    .legend-dot.dot-high   { background: var(--color-load-high); }

    .map-hint {
      text-align: center;
      color: #5a6580;
      font-size: 18px;
      font-weight: 500;
      margin: 18px 0 0;
    }

    /* ===== Мобильные устройства (до 600px) ===== */
    @media (max-width: 599px) {
      /* Мобильная версия: изменения действуют только до 599px.
         Десктопная вёрстка выше не затрагивается. */
      .site-header {
        padding: 12px 14px 14px;
        gap: 10px;
      }

      .brand {
        width: 100%;
        gap: 10px;
        min-width: 0;
      }

      .brand-logo {
        width: 68px;
        height: 68px;
        flex: 0 0 68px;
      }

      .brand-title {
        min-width: 0;
        font-size: 21px;
        line-height: 1.15;
        margin-left: 0;
        overflow-wrap: anywhere;
      }

      .role-box {
        width: 100%;
        align-items: stretch;
        gap: 8px;
      }

      .role-label {
        margin-right: 0;
        font-size: 16px;
        text-align: center;
      }

      .role-prefix { font-size: 17px; }

      .btn-role {
        width: 100%;
        margin-right: 0;
        min-height: 48px;
        padding: 10px 14px;
        font-size: 16px;
      }

      .map-section {
        width: 100%;
        padding: 12px 10px 18px;
        min-height: auto;
      }

      .map-title {
        max-width: 100%;
        white-space: normal;
        font-size: clamp(20px, 7vw, 30px);
        line-height: 1.15;
        margin: 4px auto 16px;
        transform: none;
      }

      .map-title::after {
        width: 55%;
        height: 4px;
      }

      .campus-map-wrap { border-radius: 12px; }

      .map-pin-img {
        width: clamp(54px, 18vw, 76px);
        height: clamp(54px, 18vw, 76px);
      }

      .load-legend {
        margin-top: 14px;
        padding: 12px 14px;
        font-size: 15px;
      }

      .load-legend li {
        gap: 9px;
        padding: 7px 0;
        line-height: 1.25;
      }

      .legend-dot {
        width: 14px;
        height: 14px;
      }

      .map-hint {
        font-size: 14px;
        line-height: 1.35;
        margin-top: 12px;
      }

      .admin-modal {
        top: 12px;
        right: 12px;
        width: calc(100vw - 24px);
        padding: 16px;
      }

      .admin-modal-actions {
        flex-direction: column;
      }

      .admin-modal-login,
      .admin-modal-close {
        width: 100%;
      }
    }

    /* ===== Плашка входа администратора (справа сверху) ===== */
    .admin-modal {
      position: fixed;
      top: 130px;
      right: 18px;
      z-index: 50;
      width: min(400px, calc(100vw - 24px));
      background: #ffffff;
      color: var(--color-text);
      border: 3px solid var(--color-primary);
      border-radius: var(--radius);
      box-shadow: 0 10px 30px rgba(15, 28, 77, 0.35);
      padding: 22px;
      display: none;
    }
    .admin-modal.open { display: block; }

    .admin-modal-title {
      margin: 0 0 4px;
      font-size: 21px;
      font-weight: 800;
      color: #10245c;
    }
    .admin-modal-sub { margin: 0 0 14px; font-size: 15px; color: var(--color-text-muted); }

    .admin-modal-input {
      width: 100%;
      padding: 14px 14px;
      font-size: 18px;
      border: 2px solid #ccd0dc;
      border-radius: 10px;
    }
    .admin-modal-input:focus { outline: none; border-color: var(--color-wine); }

    .admin-modal-error {
      margin: 12px 0 0;
      padding: 10px 12px;
      background: #fbe4e4;
      color: #a00;
      border-radius: 8px;
      font-size: 14px;
      display: none;
    }
    .admin-modal-error.show { display: block; }

    .admin-modal-actions {
      display: flex;
      gap: 10px;
      margin-top: 14px;
    }
    .admin-modal-login {
      flex: 1;
      padding: 13px;
      background: var(--color-wine);
      color: var(--color-cream);
      border: none;
      border-radius: 10px;
      font-size: 17px;
      font-weight: 700;
      cursor: pointer;
    }
    .admin-modal-login:hover { filter: brightness(1.1); }
    .admin-modal-close {
      padding: 13px 16px;
      background: #eef1f6;
      color: #5a6270;
      border: none;
      border-radius: 10px;
      font-size: 16px;
      cursor: pointer;
    }

    /* ===== Десктоп: чуть шире ===== */
    @media (min-width: 600px) {
      .site-header { padding: 22px 34px; }
      .role-box { flex-direction: row; align-items: center; gap: 16px; width: auto; }
      .map-section { padding: 30px; }
    }
  </style>
</head>
<body>
  <header class="site-header">
    <div class="brand">
      <a href="{{ url_for('index') }}" class="brand-logo-link" aria-label="На главную">
        <img class="brand-logo"
             src="{{ url_for('static', filename='img/logo-cafe.jpg') }}"
             alt="Логотип УрФУ Столовая">
      </a>
      <span class="brand-title">УрФУ Столовая</span>
    </div>

    <div class="role-box">
      <span class="role-label"><span class="role-prefix">Вы:</span> <strong>{{ role_name }}</strong></span>
      {% if role == 'admin' %}
        <form method="post" action="{{ url_for('logout') }}">
          <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
          <button type="submit" class="btn-role">Выйти из админки</button>
        </form>
      {% else %}
        <button type="button" class="btn-role" id="admin-login-btn">Войти как администратор</button>
      {% endif %}
    </div>
  </header>

  <main class="map-section">
    <h2 class="map-title">Столовые<br>Новокольцовского кампуса</h2>

    <!-- Карта кампуса с метками загруженности -->
    <div class="campus-map-wrap">
      <img class="campus-map-img"
           src="{{ url_for('static', filename='img/map-nvk.png') }}"
           alt="Карта Новокольцовского кампуса">

      {% for corpus in corpuses %}
        {% set pin_file = corpus.pin_files[corpus.load] %}
        <a class="map-pin"
           style="left: {{ corpus.pin_x }}%; top: {{ corpus.pin_y }}%;"
           href="{{ url_for('corpus', corpus_id=corpus.id) }}"
           title="{{ corpus.name }}">
          <img class="map-pin-img"
               src="{{ url_for('static', filename='img/' ~ pin_file) }}"
               alt="{{ corpus.name }}">
        </a>
      {% endfor %}
    </div>

    <!-- Легенда цветов -->
    <ul class="load-legend">
      <li><span class="legend-dot dot-low"></span> Свободно — можно спокойно поесть</li>
      <li><span class="legend-dot dot-medium"></span> Средняя загруженность — возможна очередь</li>
      <li><span class="legend-dot dot-high"></span> Высокая загруженность — большая очередь</li>
    </ul>

    <p class="map-hint">Чтобы отметить загруженность, выберите столовую</p>
  </main>

  {% if role != 'admin' %}
    <div class="admin-modal" id="admin-modal" role="dialog" aria-hidden="true">
      <p class="admin-modal-title">Вход для администратора</p>
      <p class="admin-modal-sub">Введите пароль</p>
      <input class="admin-modal-input" id="admin-modal-password" type="password"
             placeholder="Пароль" autocomplete="current-password">
      <p class="admin-modal-error" id="admin-modal-error">Неверный пароль. Попробуйте ещё раз.</p>
      <div class="admin-modal-actions">
        <button type="button" class="admin-modal-login" id="admin-modal-submit">Войти</button>
        <button type="button" class="admin-modal-close" id="admin-modal-close">Закрыть</button>
      </div>
    </div>
    <script defer src="{{ url_for('static', filename='js/main.js') }}"
            data-page="index"
            data-csrf="{{ csrf_token }}"></script>
  {% endif %}
</body>
</html>
"""

# ===== Страница корпуса (HTML + CSS) ===================================
CORPUS_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="icon" href="{{ url_for('static', filename='img/favicon.png') }}" type="image/png">
  <title>{{ corpus.name }} — УрФУ Столовая</title>
  <style>
    :root {
      --color-primary: #0f1c4d;
      --color-primary-light: #1c2f78;
      --color-accent: #e5b800;
      --color-bg: #e6e6e6;
      --color-text: #1a1a1a;
      --color-load-low: #2e9e4f;
      --color-load-medium: #ffbf00;
      --color-load-high: #d63333;
      --color-cream: #fbf7ee;
      --color-wine: #7c0921;
      --radius: 16px;
      --shadow: 0 4px 14px rgba(15, 28, 77, 0.12);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: system-ui, -apple-system, "Segoe UI", Arial, sans-serif;
      background: var(--color-bg);
      color: var(--color-text);
    }

    .site-header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 20px 22px;
      background: var(--color-primary);
      color: #ffffff;
    }

    .brand { display: flex; align-items: center; gap: 14px; }

    .brand-logo-link { display: inline-flex; line-height: 0; }

    .brand-logo {
      width: 125px;
      height: 125px;
      border-radius: 50%;
      object-fit: cover;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
    }

    .brand-title { font-size: 34px; font-weight: 800; margin-left: 14px; color: var(--color-cream); }

    .role-box { display: flex; align-items: center; gap: 16px; }
    .role-label { font-size: 22px; color: #d9ddee; margin-right: 20px; }
    .role-label strong { color: #ff5252; }

    .btn-back {
      background: var(--color-cream);
      color: var(--color-wine);
      border: 2px solid var(--color-wine);
      border-radius: 12px;
      font-size: 18px;
      font-weight: 800;
      line-height: 1.15;
      padding: 14px 22px;
      min-height: 58px;
      margin-right: -6px;
      text-align: center;
      cursor: pointer;
      text-decoration: none;
      box-shadow: 0 4px 10px rgba(124, 9, 33, 0.28);
      transition: transform 0.12s ease, box-shadow 0.12s ease;
    }
    .btn-back:hover {
      transform: translateY(-1px);
      box-shadow: 0 6px 14px rgba(124, 9, 33, 0.35);
    }
    .btn-back:active { transform: scale(0.96); }

    main { max-width: 600px; margin: 0 auto; padding: 22px; }

    .corpus-title { font-size: 28px; font-weight: 900; color: #10245c; margin: 8px 0 4px; }
    .corpus-location {
      color: #10245c;
      font-size: clamp(19px, 5.2vw, 37px);
      font-weight: 800;
      letter-spacing: 0.5px;
      text-align: center;
      width: fit-content;
      max-width: 100%;
      margin: 12px auto 22px;
    }
    .corpus-location::after {
      content: "";
      display: block;
      width: calc(100% - 70px);
      margin: 10px auto 0;
      height: 5px;
      border-radius: 2px;
      background: linear-gradient(90deg, var(--color-accent), var(--color-wine));
    }

    .loc-edit-btn {
      margin-left: 10px;
      padding: 6px 12px;
      font-size: 14px;
      font-weight: 700;
      background: var(--color-primary);
      color: #fff;
      border: none;
      border-radius: 8px;
      cursor: pointer;
    }
    .loc-edit-btn:hover { filter: brightness(1.15); }

    .loc-edit-panel {
      display: flex;
      align-items: center;
      gap: 10px;
      margin: -10px 0 18px;
      padding: 12px;
      background: #fff;
      border: 2px solid var(--color-primary);
      border-radius: 12px;
      flex-wrap: wrap;
    }
    .loc-edit-panel[hidden] { display: none; }
    .loc-edit-input {
      flex: 1;
      min-width: 180px;
      padding: 9px 12px;
      font-size: 15px;
      border: 2px solid #ccd0dc;
      border-radius: 8px;
    }
    .loc-edit-input:focus { outline: none; border-color: var(--color-wine); }
    .loc-save-btn {
      padding: 9px 16px;
      font-size: 15px;
      font-weight: 700;
      background: var(--color-wine);
      color: var(--color-cream);
      border: none;
      border-radius: 8px;
      cursor: pointer;
    }
    .loc-save-btn:hover { filter: brightness(1.1); }
    .loc-feedback { font-size: 13px; font-weight: 700; color: var(--color-primary); }
    .loc-feedback.error { color: #d63333; }

    .frame-box {
      padding: 14px;
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      background: #eef1f6;
      margin: 0 0 26px;
    }
    .frame-box.plain { border: none; }

    .card-img {
      display: none;
      width: 100%;
      height: 168px;
      object-fit: cover;
      object-position: center;
      border-radius: var(--radius);
    }
    .load-card.load-low    .card-img-low { display: block; animation: cardFade 0.8s ease; }
    .load-card.load-medium .card-img-medium { display: block; animation: cardFade 0.8s ease; }
    .load-card.load-high   .card-img-high { display: block; animation: cardFade 0.8s ease; }

    @keyframes cardFade {
      from { opacity: 0; transform: scale(0.96); }
      to   { opacity: 1; transform: scale(1); }
    }

    .menu-open-btn {
      display: block;
      width: 100%;
      padding: 0;
      border: none;
      background: none;
      cursor: pointer;
      border-radius: var(--radius);
      overflow: hidden;
      transition: transform 0.12s ease;
    }
    .menu-image {
      display: block;
      width: 100%;
      height: 124px;
      object-fit: cover;
      object-position: center;
    }
    .menu-open-btn:hover { transform: scale(1.05); }
    .menu-open-btn:hover .menu-image { filter: brightness(1.05); }
    .menu-open-btn:active { transform: scale(0.98); }

    /* ===== Модальное окно меню (Этап 3): bottom sheet ===== */
    .menu-modal-overlay {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(15, 28, 77, 0.55);
      z-index: 100;
      display: none;
      align-items: flex-end;
      justify-content: center;
      padding: 135px 0 0;
    }
    .menu-modal-overlay.open { display: flex; }

    .menu-modal {
      width: min(600px, 100%);
      max-height: calc(100vh - 141px);
      display: flex;
      flex-direction: column;
      background: #ffffff;
      color: var(--color-text);
      border-radius: var(--radius) var(--radius) 0 0;
      box-shadow: 0 -8px 40px rgba(15, 28, 77, 0.4);
      overflow: hidden;
      animation: menuSlideUp 0.35s cubic-bezier(0.22, 0.9, 0.25, 1);
    }
    @keyframes menuSlideUp {
      from { transform: translateY(100%); }
      to   { transform: translateY(0); }
    }

    .menu-modal-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 18px 22px;
      background: var(--color-primary);
      color: var(--color-cream);
    }
    .menu-modal-title { font-size: 24px; font-weight: 800; margin: 0; }
    .menu-modal-sub { font-size: 14px; color: #d9ddee; margin-top: 2px; }
    .menu-modal-close {
      background: none;
      border: none;
      color: var(--color-cream);
      font-size: 30px;
      line-height: 1;
      cursor: pointer;
      padding: 0 4px;
    }
    .menu-modal-close:hover { color: #ffffff; }

    .menu-modal-body {
      padding: 18px 22px;
      overflow-y: auto;
    }

    .menu-category {
      margin-bottom: 22px;
    }
    .menu-category-head {
      display: flex;
      align-items: center;
      gap: 10px;
      border-bottom: 3px solid var(--color-accent);
      padding-bottom: 6px;
      margin-bottom: 10px;
    }
    .menu-cat-name { font-size: 20px; font-weight: 800; color: #10245c; margin: 0; flex: 1; }
    .menu-cat-hidden-tag {
      font-size: 12px;
      font-weight: 700;
      color: #7a8090;
      background: #eef1f6;
      padding: 2px 8px;
      border-radius: 999px;
    }
    .menu-category.unavailable .menu-cat-name {
      color: #9aa0ad;
      text-decoration: line-through;
    }

    .menu-item {
      padding: 8px 4px;
      border-bottom: 1px solid #e6e6e6;
    }
    .menu-item:last-child { border-bottom: none; }
    .menu-item.unavailable { opacity: 0.55; }
    .menu-item.unavailable .menu-item-name { color: #9aa0ad; }
    .menu-item.unavailable .menu-item-price {
      color: #9aa0ad;
      text-decoration: line-through;
    }
    .menu-item-top {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
    }
    .menu-item-name { font-size: 17px; font-weight: 700; color: var(--color-text); }
    .menu-item-hidden-tag {
      font-size: 11px;
      font-weight: 700;
      color: #7a8090;
      background: #eef1f6;
      padding: 1px 7px;
      border-radius: 999px;
      margin-left: 8px;
    }
    .menu-item-price { font-size: 17px; font-weight: 800; color: var(--color-wine); white-space: nowrap; }
    .menu-item-desc { font-size: 14px; color: #5a6580; margin-top: 3px; }
    .menu-item-admin {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-top: 8px;
    }
    .menu-item-admin .menu-btn { padding: 4px 10px; font-size: 12px; }

    .menu-empty {
      text-align: center;
      color: #7a8090;
      font-size: 16px;
      padding: 30px 10px;
    }

    /* Админ-панель */
    .menu-modal [hidden] { display: none !important; }
    .menu-modal-actions {
      display: flex;
      gap: 10px;
      padding: 14px 22px;
      border-top: 1px solid #e6e6e6;
      background: #fbf7ee;
      flex-wrap: wrap;
    }
    .menu-modal-actions[hidden], .menu-admin-note[hidden], .menu-form[hidden], .menu-form-cat-wrap[hidden] { display: none !important; }
    .menu-admin-note {
      font-size: 14px;
      color: #7a8090;
      padding: 14px 22px;
      border-top: 1px solid #e6e6e6;
      background: #fbf7ee;
      text-align: center;
    }

    .menu-btn {
      border: none;
      border-radius: 10px;
      font-size: 14px;
      font-weight: 800;
      padding: 10px 14px;
      cursor: pointer;
    }
    .menu-btn:hover { filter: brightness(1.08); }
    .menu-btn.primary { background: var(--color-wine); color: var(--color-cream); }
    .menu-btn.secondary { background: var(--color-primary); color: var(--color-cream); }
    .menu-btn.ghost { background: #eef1f6; color: var(--color-text); }
    .menu-btn.danger { background: #fbe4e4; color: #a00; }

    /* Формы добавления/редактирования */
    .menu-form {
      display: none;
      flex-direction: column;
      gap: 10px;
      padding: 14px 22px;
      border-top: 1px solid #e6e6e6;
      background: #fbf7ee;
    }
    .menu-form.open { display: flex; }
    .menu-form-title { font-size: 16px; font-weight: 800; color: #10245c; margin: 0; }
    .menu-form select, .menu-form input {
      width: 100%;
      padding: 10px 12px;
      font-size: 15px;
      border: 2px solid #ccd0dc;
      border-radius: 8px;
    }
    .menu-form input:focus, .menu-form select:focus { outline: none; border-color: var(--color-wine); }
    .menu-form-row { display: flex; gap: 10px; flex-wrap: wrap; }
    .menu-form-row > div { flex: 1; min-width: 120px; }
    .menu-form-actions { display: flex; gap: 10px; justify-content: flex-end; }
    .menu-form-error { color: #a00; font-size: 13px; font-weight: 700; min-height: 0; }

    .report-title { font-size: 24px; font-weight: 800; color: #10245c; margin: 0 0 4px; text-align: center; }

    .report-options {
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding: 18px;
      border-radius: var(--radius);
      background: #eef1f6;
    }

    .report-btn {
      border: none;
      padding: 0;
      border-radius: var(--radius);
      overflow: hidden;
      cursor: pointer;
      background: none;
      position: relative;
      transition: transform 0.12s ease, box-shadow 0.12s ease;
    }
    .report-btn:hover { transform: scale(1.03); }
    .report-btn.medium { transform: scale(1.01); }
    .report-btn.medium:hover { transform: scale(1.07); }
    .report-btn:active { transform: scale(0.96); }
    .report-btn:disabled { opacity: 0.7; cursor: default; }
    .rbtn-img { display: block; width: 100%; height: auto; }

    .hover-dot {
      position: absolute;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35);
      transform: translate(-50%, -50%);
      opacity: 0;
      transition: opacity 0.2s ease;
      pointer-events: none;
    }
    .report-btn:hover .hover-dot { opacity: 1; }
    .report-btn.low .hover-dot    { left: 5.7%; top: 52%; background: #eef1f6; }
    .report-btn.medium .hover-dot { left: 6.4%; top: 53%; background: #eef1f6; }
    .report-btn.high .hover-dot   { left: 6.2%; top: 48.3%; background: #eef1f6; }

    .report-feedback {
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      font-size: 18px;
      font-weight: 700;
      color: #7a8090;
      text-align: center;
      opacity: 0;
      visibility: hidden;
      transition: opacity 0.6s ease, visibility 0.6s ease;
      pointer-events: none;
    }
    .report-feedback.show {
      opacity: 1;
      visibility: visible;
    }

    footer {
      position: relative;
      text-align: center;
      padding: 0 14px 14px;
      color: #7a8090;
      font-size: 18px;
      font-weight: 700;
    }
    .footer-text { display: inline-block; transition: opacity 0.3s ease; }
    footer.fb-shown .footer-text { opacity: 0; }

    @media (max-width: 599px) {
      /* Мобильная версия: изменения действуют только до 599px.
         Десктопная вёрстка выше не затрагивается. */
      .site-header {
        padding: 12px 14px 14px;
        gap: 10px;
      }

      .brand {
        width: 100%;
        gap: 10px;
        min-width: 0;
      }

      .brand-logo {
        width: 68px;
        height: 68px;
        flex: 0 0 68px;
      }

      .brand-title {
        min-width: 0;
        font-size: 21px;
        line-height: 1.15;
        margin-left: 0;
        overflow-wrap: anywhere;
      }

      .role-box {
        width: 100%;
        flex-direction: column;
        align-items: stretch;
        gap: 8px;
      }

      .role-label {
        margin-right: 0;
        font-size: 16px;
        text-align: center;
      }

      .btn-back {
        width: 100%;
        margin-right: 0;
        min-height: 48px;
        padding: 10px 14px;
        font-size: 16px;
        display: flex;
        align-items: center;
        justify-content: center;
      }

      main {
        width: 100%;
        padding: 14px 10px 18px;
      }

      .corpus-title {
        font-size: 22px;
      }

      .corpus-location {
        width: 100%;
        font-size: clamp(20px, 7vw, 30px);
        line-height: 1.15;
        margin: 8px auto 16px;
        overflow-wrap: anywhere;
      }

      .corpus-location::after {
        width: 55%;
        height: 4px;
      }

      .loc-edit-btn {
        margin-left: 4px;
        padding: 5px 9px;
        font-size: 13px;
        vertical-align: middle;
      }

      .loc-edit-panel {
        align-items: stretch;
        padding: 10px;
        gap: 8px;
      }

      .loc-edit-input {
        min-width: 0;
        width: 100%;
        flex-basis: 100%;
      }

      .loc-save-btn { width: 100%; }

      .frame-box {
        padding: 8px;
        margin-bottom: 14px;
        border-radius: 12px;
      }

      .card-img {
        height: auto;
        min-height: 0;
      }

      .menu-image {
        height: auto;
        min-height: 76px;
      }

      .menu-open-btn:hover { transform: none; }

      .report-options {
        gap: 8px;
        padding: 10px;
        border-radius: 12px;
      }

      .report-title {
        font-size: 19px;
        line-height: 1.2;
      }

      .report-btn:hover { transform: none; }
      .report-btn.medium { transform: none; }
      .report-btn.medium:hover { transform: none; }

      .menu-modal-overlay {
        padding: 0;
      }

      .menu-modal {
        width: 100%;
        max-height: 100dvh;
        border-radius: 14px 14px 0 0;
      }

      .menu-modal-head {
        padding: 14px 16px;
      }

      .menu-modal-title { font-size: 21px; }
      .menu-modal-close { font-size: 28px; }

      .menu-modal-body {
        padding: 14px 16px;
        -webkit-overflow-scrolling: touch;
      }

      .menu-category-head {
        align-items: flex-start;
      }

      .menu-cat-name { font-size: 18px; }

      .menu-item-top {
        align-items: flex-start;
        gap: 8px;
      }

      .menu-item-name,
      .menu-item-price { font-size: 15px; }

      .menu-item-desc { font-size: 13px; }

      .menu-modal-actions,
      .menu-form {
        padding: 12px 16px;
      }

      .menu-modal-actions {
        flex-direction: column;
      }

      .menu-modal-actions .menu-btn,
      .menu-form-actions .menu-btn {
        width: 100%;
      }

      .menu-form-row > div {
        min-width: 100%;
      }

      footer {
        font-size: 14px;
        padding-bottom: 12px;
      }
    }
    @media (min-width: 600px) {
      .site-header { padding: 22px 34px; }
      main { padding: 30px; }
      .menu-modal-overlay { padding-top: 175px; }
      .menu-modal { max-height: calc(100vh - 181px); }
    }
  </style>
</head>
<body>
  <header class="site-header">
    <div class="brand">
      <a href="{{ url_for('index') }}" class="brand-logo-link" aria-label="На главную">
        <img class="brand-logo"
             src="{{ url_for('static', filename='img/logo-cafe.jpg') }}"
             alt="Логотип УрФУ Столовая">
      </a>
      <span class="brand-title">{{ corpus.name }}</span>
    </div>
    <div class="role-box">
      <span class="role-label"><strong>{{ 'Административный режим' if role == 'admin' else 'Гостевой режим' }}</strong></span>
      <a class="btn-back" href="{{ url_for('index') }}">← Назад на главную</a>
    </div>
  </header>

  <main>
    <p class="corpus-location">
      <span id="canteen-location">Столовая, {{ corpus.canteen_location }}</span>
      {% if role == 'admin' %}
        <button type="button" class="loc-edit-btn" id="loc-edit-btn">Изменить</button>
      {% endif %}
    </p>

    {% if role == 'admin' %}
      <div class="loc-edit-panel" id="loc-edit-panel" hidden>
        <input class="loc-edit-input" id="loc-edit-input" type="text"
               value="{{ corpus.canteen_location }}" maxlength="120">
        <button type="button" class="loc-save-btn" id="loc-save-btn">Сохранить</button>
        <span class="loc-feedback" id="loc-feedback"></span>
      </div>
    {% endif %}

    <div class="frame-box">
      <div class="load-card load-{{ corpus.load }}" id="load-card">
        <img class="card-img card-img-low" src="{{ url_for('static', filename='img/card-load-low.png') }}"
             alt="Свободно">
        <img class="card-img card-img-medium" src="{{ url_for('static', filename='img/card-load-medium.png') }}"
             alt="Средне">
        <img class="card-img card-img-high" src="{{ url_for('static', filename='img/card-load-high.png') }}"
             alt="Много народу">
      </div>
    </div>

    <div class="frame-box plain">
      <button type="button" class="menu-open-btn" id="menu-open-btn" aria-label="Открыть меню" aria-haspopup="dialog">
        <img class="menu-image" src="{{ url_for('static', filename='img/menu.png') }}"
             alt="Меню">
      </button>
    </div>

    <div class="report-options">
      <h2 class="report-title">Оцените загруженность сейчас</h2>
      <button class="report-btn low" data-load="low" type="button" aria-label="Свободно">
        <img class="rbtn-img" src="{{ url_for('static', filename='img/btn-load-low.png') }}" alt="Свободно">
        <span class="hover-dot"></span>
      </button>
      <button class="report-btn medium" data-load="medium" type="button" aria-label="Средне">
        <img class="rbtn-img" src="{{ url_for('static', filename='img/btn-load-medium.png') }}" alt="Средне">
        <span class="hover-dot"></span>
      </button>
      <button class="report-btn high" data-load="high" type="button" aria-label="Много народу">
        <img class="rbtn-img" src="{{ url_for('static', filename='img/btn-load-high.png') }}" alt="Много народу">
        <span class="hover-dot"></span>
      </button>
    </div>
  </main>

  <footer>
    <div class="report-feedback" id="report-feedback">Спасибо, обновили!</div>
    <span class="footer-text" id="footer-text">УрФУ Столовая</span>
  </footer>

  <!-- Модальное окно меню (Этап 3) -->
  <div class="menu-modal-overlay" id="menu-modal" role="dialog" aria-modal="true"
       aria-labelledby="menu-modal-title" aria-hidden="true">
    <div class="menu-modal">
      <div class="menu-modal-head">
        <div>
          <h2 class="menu-modal-title" id="menu-modal-title">Меню</h2>
          <p class="menu-modal-sub" id="menu-modal-sub">{{ corpus.name }}</p>
        </div>
        <button type="button" class="menu-modal-close" id="menu-modal-close" aria-label="Закрыть меню">&times;</button>
      </div>
      <div class="menu-modal-body" id="menu-modal-body">
        <p class="menu-empty" id="menu-loading">Загружаем меню…</p>
      </div>
      <div class="menu-admin-note" id="menu-guest-note" hidden>
        Чтобы изменить меню — войдите как администратор.
      </div>
      <div class="menu-modal-actions" id="menu-admin-actions" hidden>
        <button type="button" class="menu-btn primary" id="menu-add-item-btn">+ Добавить блюдо</button>
        <button type="button" class="menu-btn secondary" id="menu-add-cat-btn">+ Добавить категорию</button>
      </div>
      <div class="menu-form" id="menu-form">
        <p class="menu-form-title" id="menu-form-title"></p>
        <div class="menu-form-row">
          <div>
            <label for="menu-form-name">Название</label>
            <input id="menu-form-name" type="text" maxlength="60">
          </div>
          <div id="menu-form-price-wrap">
            <label for="menu-form-price">Цена</label>
            <input id="menu-form-price" type="number" min="0">
          </div>
        </div>
        <div id="menu-form-desc-wrap">
          <label for="menu-form-desc">Описание</label>
          <input id="menu-form-desc" type="text" maxlength="200">
        </div>
        <div id="menu-form-cat-wrap" hidden>
          <label for="menu-form-cat">Категория</label>
          <select id="menu-form-cat"></select>
        </div>
        <p class="menu-form-error" id="menu-form-error"></p>
        <div class="menu-form-actions">
          <button type="button" class="menu-btn ghost" id="menu-form-cancel">Отмена</button>
          <button type="button" class="menu-btn primary" id="menu-form-save">Сохранить</button>
        </div>
      </div>
    </div>
  </div>

  <script defer src="{{ url_for('static', filename='js/main.js') }}"
          data-corpus="{{ corpus.id }}"
          data-is-admin="{{ '1' if role == 'admin' else '0' }}"
          data-csrf="{{ csrf_token }}"></script>
</body>
</html>
"""

# ===== Flask-приложение и маршруты =====================================
app = Flask(__name__)
# Секретный ключ нужен для сессий. В проде задаётся через SECRET_KEY,
# для разработки — случайный ключ на каждый запуск.
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(16)


# CSRF-защита: применяется ко всем мутирующим запросам.
@app.before_request
def csrf_guard():
    result = _csrf_protect()
    if result is not None:
        return result
    return None


def role_info():
    """Возвращает (role, role_name) — текущую роль и её название."""
    role = session.get("role", "guest")
    return role, "Гость" if role == "guest" else "Админ"


@app.route("/")
def index():
    role, role_name = role_info()
    corpuses = [corpus_dict(entry) for entry in _CORPS]
    return render_template_string(
        INDEX_HTML, corpuses=corpuses, role=role, role_name=role_name,
        csrf_token=get_csrf_token(),
    )


@app.route("/corpus/<corpus_id>")
def corpus(corpus_id):
    entry = corpus_by_id(corpus_id)
    if entry is None:
        return "Корпус не найден", 404
    data = corpus_dict(entry)
    role, role_name = role_info()
    load_name, load_desc = LOAD_DESCRIPTIONS[data["load"]]
    return render_template_string(
        CORPUS_HTML, corpus=data, role=role, role_name=role_name,
        load_name=load_name, load_desc=load_desc,
        csrf_token=get_csrf_token(),
    )


@app.route("/corpus/<corpus_id>/report-load", methods=["POST"])
def report_load(corpus_id):
    entry = corpus_by_id(corpus_id)
    if entry is None:
        return jsonify({"error": "Корпус не найден"}), 404
    payload = request.get_json(silent=True) or {}
    new_load = payload.get("load")
    if new_load not in ("low", "medium", "high"):
        return jsonify({"error": "Недопустимое значение load"}), 400
    # Простая защита от накрутки: не чаще одной оценки в 3 секунды с IP/cессии.
    now = time.time()
    last = session.get("_last_report", 0)
    if now - last < 3:
        return jsonify({"error": "Слишком часто! Подождите пару секунд."}), 429
    session["_last_report"] = now
    _CURRENT_LOADS[corpus_id] = new_load
    _save_json(_LOAD_FILE, _CURRENT_LOADS)
    load_name, load_desc = LOAD_DESCRIPTIONS[new_load]
    return jsonify({"load": new_load, "load_name": load_name, "load_desc": load_desc})


@app.route("/corpus/<corpus_id>/canteen-location", methods=["POST"])
def canteen_location(corpus_id):
    # Менять расположение может только администратор.
    if session.get("role") != "admin":
        return jsonify({"error": "Нужен административный режим"}), 403
    entry = corpus_by_id(corpus_id)
    if entry is None:
        return jsonify({"error": "Корпус не найден"}), 404
    payload = request.get_json(silent=True) or {}
    new_location = (payload.get("canteen_location") or "").strip()
    if not new_location:
        return jsonify({"error": "Расположение не может быть пустым"}), 400
    if len(new_location) > 120:
        return jsonify({"error": "Слишком длинное расположение"}), 400
    _CURRENT_LOCATIONS[corpus_id] = new_location
    _save_json(_LOCATIONS_FILE, _CURRENT_LOCATIONS)
    return jsonify({"canteen_location": new_location})


@app.route("/corpus/<corpus_id>/menu")
def menu(corpus_id):
    # Этап 3: меню отдаётся как JSON для всплывающего окна на странице корпуса.
    entry = corpus_by_id(corpus_id)
    if entry is None:
        return jsonify({"error": "Корпус не найден"}), 404
    visible_only = session.get("role") != "admin"
    return jsonify(_visible_menu(corpus_id, visible_only))


def _visible_menu(corpus_id, visible_only):
    """Возвращает меню корпуса. Гостям (visible_only=True) — только видимые
    категории и скрытые блюда внутри видимых категорий помечаются как
    «нет в наличии». Администратору — всё, включая невидимые категории."""
    result = []
    for cat in _CURRENT_MENU.get(corpus_id, []):
        if visible_only and not cat["visible"]:
            continue
        result.append({
            "id": cat["id"],
            "name": cat["name"],
            "visible": cat["visible"],
            "items": [
                {
                    "id": i["id"],
                    "name": i["name"],
                    "price": i["price"],
                    "description": i["description"],
                    "visible": i["visible"],
                }
                for i in cat["items"]
            ],
        })
    return result


def _require_admin():
    if session.get("role") != "admin":
        return jsonify({"error": "Нужен административный режим"}), 403
    return None


def _find_category(corpus_id, cat_id):
    for cat in _CURRENT_MENU.get(corpus_id, []):
        if cat["id"] == cat_id:
            return cat
    return None


def _new_id(prefix):
    """Генерирует уникальный id на основе существующих id категорий и блюд меню."""
    used = set()
    for cats in _CURRENT_MENU.values():
        for c in cats:
            used.add(c["id"])
            used.update(i["id"] for i in c["items"])
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


@app.route("/corpus/<corpus_id>/menu/categories", methods=["POST"])
def add_category(corpus_id):
    err = _require_admin()
    if err:
        return err
    if corpus_by_id(corpus_id) is None:
        return jsonify({"error": "Корпус не найден"}), 404
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Название категории не может быть пустым"}), 400
    if len(name) > 60:
        return jsonify({"error": "Слишком длинное название категории"}), 400
    cat_id = _new_id("cat")
    category = {"id": cat_id, "name": name, "visible": True, "items": []}
    _CURRENT_MENU.setdefault(corpus_id, []).append(category)
    _save_menu_normalized()
    return jsonify({"category": category})


@app.route("/corpus/<corpus_id>/menu/categories/<cat_id>", methods=["PUT", "DELETE", "PATCH"])
def manage_category(corpus_id, cat_id):
    err = _require_admin()
    if err:
        return err
    if corpus_by_id(corpus_id) is None:
        return jsonify({"error": "Корпус не найден"}), 404
    cat = _find_category(corpus_id, cat_id)
    if cat is None:
        return jsonify({"error": "Категория не найдена"}), 404
    if request.method == "DELETE":
        _CURRENT_MENU[corpus_id] = [c for c in _CURRENT_MENU.get(corpus_id, []) if c["id"] != cat_id]
        _save_menu_normalized()
        return jsonify({"ok": True})
    payload = request.get_json(silent=True) or {}
    if request.method == "PATCH":
        # PATCH используется для переключения видимости
        if "visible" in payload:
            cat["visible"] = bool(payload["visible"])
        _save_menu_normalized()
        return jsonify({"category": cat})
    # PUT — изменение названия
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Название категории не может быть пустым"}), 400
    cat["name"] = name
    _save_menu_normalized()
    return jsonify({"category": cat})


@app.route("/corpus/<corpus_id>/menu/items", methods=["POST"])
def add_item(corpus_id):
    err = _require_admin()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    cat_id = (payload.get("category_id") or "").strip()
    cat = _find_category(corpus_id, cat_id)
    if cat is None:
        return jsonify({"error": "Категория не найдена"}), 404
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Название блюда не может быть пустым"}), 400
    try:
        price = int(float(payload.get("price", 0)))
    except (TypeError, ValueError):
        return jsonify({"error": "Некорректная цена"}), 400
    if price < 0:
        return jsonify({"error": "Цена не может быть отрицательной"}), 400
    item_id = _new_id("it")
    item = {
        "id": item_id,
        "name": name,
        "price": price,
        "description": (payload.get("description") or "").strip(),
        "visible": True,
    }
    cat["items"].append(item)
    _save_menu_normalized()
    return jsonify({"item": item})


@app.route("/corpus/<corpus_id>/menu/items/<item_id>", methods=["PUT", "DELETE", "PATCH"])
def manage_item(corpus_id, item_id):
    err = _require_admin()
    if err:
        return err
    if corpus_by_id(corpus_id) is None:
        return jsonify({"error": "Корпус не найден"}), 404
    for cat in _CURRENT_MENU.get(corpus_id, []):
        for item in cat["items"]:
            if item["id"] == item_id:
                if request.method == "DELETE":
                    cat["items"] = [i for i in cat["items"] if i["id"] != item_id]
                    _save_menu_normalized()
                    return jsonify({"ok": True})
                payload = request.get_json(silent=True) or {}
                if request.method == "PATCH":
                    # PATCH — переключение видимости
                    if "visible" in payload:
                        item["visible"] = bool(payload["visible"])
                    _save_menu_normalized()
                    return jsonify({"item": item})
                # PUT — изменение полей блюда
                name = (payload.get("name") or "").strip()
                if not name:
                    return jsonify({"error": "Название блюда не может быть пустым"}), 400
                try:
                    price = int(float(payload.get("price", item["price"])))
                except (TypeError, ValueError):
                    return jsonify({"error": "Некорректная цена"}), 400
                if price < 0:
                    return jsonify({"error": "Цена не может быть отрицательной"}), 400
                item["name"] = name
                item["price"] = price
                item["description"] = (payload.get("description") or "").strip()
                _save_menu_normalized()
                return jsonify({"item": item})
    return jsonify({"error": "Блюдо не найдено"}), 404


@app.route("/login", methods=["POST"])
def login():
    # Отдельной страницы входа нет — плашка на главной шлёт сюда JSON.
    payload = request.get_json(silent=True) or request.form
    password = (payload.get("password") or "").strip()
    if check_password_hash(_ADMIN_PASSWORD_HASH, password):
        session["role"] = "admin"
        return jsonify({"ok": True})
    return jsonify({"error": "Неверный пароль"}), 401


@app.route("/logout", methods=["POST"])
def logout():
    session["role"] = "guest"
    return redirect(url_for("index"))


if __name__ == "__main__":
    # Режим отладки включается только через FLASK_DEBUG=1 (для разработки).
    # По умолчанию выключен — debugger запрещён в боевом запуске.
    debug = os.environ.get("FLASK_DEBUG", "").strip().lower() in ("1", "true", "yes")
    port = int(os.environ.get("PORT", 80))
    app.run(host="0.0.0.0", port=port, debug=debug)