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
    """Сохраняет данные в JSON-файл."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# Считываем актуальные load и расположения один раз при старте приложения.
_CURRENT_LOADS = _load_json(_LOAD_FILE, DEFAULT_LOADS)
_CURRENT_LOCATIONS = _load_json(_LOCATIONS_FILE, DEFAULT_LOCATIONS)


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

# ===== Страница (HTML + CSS) ============================================
INDEX_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
      justify-content: center;
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
      .brand-logo { width: 90px; height: 90px; }
      .brand-title { font-size: 24px; margin-left: 6px; }
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

    /* ===== Анимация перехода между страницами ===== */
    body {
      animation: pageIn 0.3s ease;
    }
    body.page-exit {
      opacity: 0;
      transform: translateY(-10px);
      transition: opacity 0.15s ease, transform 0.15s ease;
    }
    @keyframes pageIn {
      from { opacity: 0; transform: translateY(12px); }
      to   { opacity: 1; transform: translateY(0); }
    }
  </style>
</head>
<body>
  <header class="site-header">
    <div class="brand">
      <img class="brand-logo"
           src="{{ url_for('static', filename='img/logo-cafe.jpg') }}"
           alt="Логотип УрФУ Столовая">
      <span class="brand-title">УрФУ Столовая</span>
    </div>

    <div class="role-box">
      <span class="role-label"><span class="role-prefix">Вы:</span> <strong>{{ role_name }}</strong></span>
      {% if role == 'admin' %}
        <form method="post" action="{{ url_for('logout') }}">
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
            data-page="index"></script>
  {% endif %}
  <script defer src="{{ url_for('static', filename='js/page-transition.js') }}"></script>
</body>
</html>
"""

# ===== Страница корпуса (HTML + CSS) ===================================
CORPUS_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
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

    .brand-logo {
      width: 100px;
      height: 100px;
      border-radius: 50%;
      object-fit: cover;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
    }

    .brand-title { font-size: 26px; font-weight: 800; margin-left: 10px; color: var(--color-cream); }

    .role-label { font-size: 20px; color: #d9ddee; margin-right: 30px; }
    .role-label strong { color: #ff5252; }

    .btn-back {
      background: var(--color-cream);
      color: var(--color-wine);
      border: 2px solid var(--color-wine);
      border-radius: 12px;
      font-size: 17px;
      font-weight: 800;
      padding: 12px 20px;
      cursor: pointer;
      text-decoration: none;
    }
    .btn-back:hover { box-shadow: 0 4px 10px rgba(124, 9, 33, 0.28); }

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

.menu-image {
      display: block;
      width: 100%;
      height: 124px;
      object-fit: cover;
      object-position: center;
      transition: transform 0.12s ease;
    }
    .frame-box.plain a:hover .menu-image { transform: scale(1.05); }
    .frame-box.plain a:active .menu-image { transform: scale(0.98); }
    .menu-image:hover { filter: brightness(1.05); }

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
      .brand-logo { width: 80px; height: 80px; }
      .brand-title { font-size: 21px; margin-left: 6px; }
    }
    @media (min-width: 600px) {
      .site-header { padding: 22px 34px; }
      main { padding: 30px; }
    }

    /* ===== Анимация перехода между страницами ===== */
    body {
      animation: pageIn 0.3s ease;
    }
    body.page-exit {
      opacity: 0;
      transform: translateY(-10px);
      transition: opacity 0.15s ease, transform 0.15s ease;
    }
    @keyframes pageIn {
      from { opacity: 0; transform: translateY(12px); }
      to   { opacity: 1; transform: translateY(0); }
    }
  </style>
</head>
<body>
  <header class="site-header">
    <div class="brand">
      <img class="brand-logo"
           src="{{ url_for('static', filename='img/logo-cafe.jpg') }}"
           alt="Логотип УрФУ Столовая">
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
        <button type="button" class="loc-edit-btn" id="loc-edit-btn">✏️ Изменить</button>
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
      <a href="{{ url_for('menu', corpus_id=corpus.id) }}" aria-label="Меню">
        <img class="menu-image" src="{{ url_for('static', filename='img/menu.png') }}"
             alt="Меню">
      </a>
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
  <script defer src="{{ url_for('static', filename='js/main.js') }}"
          data-corpus="{{ corpus.id }}"></script>
  <script defer src="{{ url_for('static', filename='js/page-transition.js') }}"></script>
</body>
</html>
"""

# ===== Страница-заглушка меню (Этап 3) =================================
MENU_STUB_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Меню — {{ corpus.name }}</title>
  <style>
    :root { --color-primary: #0f1c4d; --color-cream: #fbf7ee; --color-wine: #7c0921; }
    * { box-sizing: border-box; }
    body {
      margin: 0; font-family: system-ui, -apple-system, "Segoe UI", Arial, sans-serif;
      background: #e6e6e6; color: #1a1a1a; text-align: center;
    }
    .wrap { max-width: 600px; margin: 0 auto; padding: 60px 22px; }
    h1 { color: #10245c; }
    p { font-size: 18px; }
    a { display: inline-block; margin-top: 20px; color: var(--color-wine); font-weight: 700; }

    body {
      animation: pageIn 0.3s ease;
    }
    body.page-exit {
      opacity: 0;
      transform: translateY(-10px);
      transition: opacity 0.15s ease, transform 0.15s ease;
    }
    @keyframes pageIn {
      from { opacity: 0; transform: translateY(12px); }
      to   { opacity: 1; transform: translateY(0); }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Меню «{{ corpus.name }}»</h1>
    <p>Меню появится на этапе 3.</p>
    <a href="{{ url_for('corpus', corpus_id=corpus.id) }}">← Назад к столовой</a>
  </div>
  <script defer src="{{ url_for('static', filename='js/page-transition.js') }}"></script>
</body>
</html>
"""

# ===== Flask-приложение и маршруты =====================================
app = Flask(__name__)
# Секретный ключ нужен для сессий. В проде задаётся через SECRET_KEY,
# для разработки — случайный ключ на каждый запуск.
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(16)


def role_info():
    """Возвращает (role, role_name) — текущую роль и её название."""
    role = session.get("role", "guest")
    return role, "Гость" if role == "guest" else "Админ"


@app.route("/")
def index():
    role, role_name = role_info()
    corpuses = [corpus_dict(entry) for entry in _CORPS]
    return render_template_string(INDEX_HTML, corpuses=corpuses, role=role, role_name=role_name)


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
    # Этап 3: полноценная страница меню. Пока — заглушка.
    entry = corpus_by_id(corpus_id)
    if entry is None:
        return "Корпус не найден", 404
    data = corpus_dict(entry)
    return render_template_string(MENU_STUB_HTML, corpus=data)


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
    # debug=True — удобно на время разработки, выключить перед боевым запуском
    app.run(debug=True)