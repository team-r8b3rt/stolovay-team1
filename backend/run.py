# -*- coding: utf-8 -*-
"""
УрФУ Столовая — сайт загруженности столовых.

Структура проекта (backend/):
  run.py            — этот файл: сервер и вся логика на Python
  templates/        — HTML-страницы (index.html, corpus.html)
  static/           — картинки и скрипты (css внутри шаблонов, js в static/js)
  data/             — «живые» данные (загруженность, меню), создаются при старте

Запуск:  python run.py
Открыть: http://127.0.0.1:5000/
"""
import json
import os
import secrets
import threading
import time

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

# ===== Папки проекта =====================================================
# Все папки задаём явно (относительно этого файла), чтобы сервер работал
# независимо от того, из какой папки его запустили.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_BASE_DIR, "data")

app = Flask(
    __name__,
    template_folder=os.path.join(_BASE_DIR, "templates"),
    static_folder=os.path.join(_BASE_DIR, "static"),
)

app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(16)

# Секретный ключ нужен для сессий (кто сейчас «работник», CSRF-токен и т.д.).
# В реальном проекте задаётся через переменную окружения SECRET_KEY.

# ===== Данные о корпусах ================================================
# Статика (имена, расположение, позиции меток) — здесь.
# «Живое» состояние (загруженность, расположение, меню) — в JSON-файлах
# папки data/, чтобы его можно было менять без правки кода.


def _make_pins(corpus_code):
    """Имена пин-картинок для метки корпуса: {low, medium, high -> файл}."""
    return {level: f"pin-{level}-{corpus_code}.png" for level in ("low", "medium", "high")}


# (имя, код, расположение столовой, загрузка по умолчанию, x метки, y метки)
_CORPS = [
    ("ИРИТ-РТФ", "irit", "2 этаж, крыло Б", "low", 46, 23),
    ("ИнЭУ",     "ineu", "1 этаж, справа от входа", "medium", 82, 13),
    ("ОЦК",      "cimt", "2 этаж, атриум", "high", 17, 70),
]

_LOAD_FILE = os.path.join(_DATA_DIR, "load.json")
_LOCATIONS_FILE = os.path.join(_DATA_DIR, "locations.json")
_MENU_FILE = os.path.join(_DATA_DIR, "menu.json")

# При старте гарантируем, что папка с данными существует.
os.makedirs(_DATA_DIR, exist_ok=True)

# Блокировка нужна, чтобы два запроса не записывали JSON-файл одновременно.
_IO_LOCK = threading.Lock()


# Значения по умолчанию — fallback, если JSON-файл отсутствует или битый.
DEFAULT_LOADS = {code: load for name, code, loc, load, x, y in _CORPS}
DEFAULT_LOCATIONS = {code: loc for name, code, loc, load, x, y in _CORPS}


def _load_json(path, defaults):
    """Читает JSON-файл. Отсутствующие ключи дополняет значениями по умолчанию."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {code: data.get(code, d) for code, d in defaults.items()}
    except (OSError, ValueError):
        return defaults


def _save_json(path, data):
    """Потокобезопасно сохраняет данные в JSON-файл (сначала во временный файл)."""
    with _IO_LOCK:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)


# Актуальные значения загруженности и расположений, загруженные при старте.
_CURRENT_LOADS = _load_json(_LOAD_FILE, DEFAULT_LOADS)
_CURRENT_LOCATIONS = _load_json(_LOCATIONS_FILE, DEFAULT_LOCATIONS)


def _load_menu():
    """Читает меню из JSON-файла. При ошибке — пустое меню для всех корпусов."""
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
    """Приводит меню к корректной структуре: категории с items и id/visible/name."""
    normalized = {}
    for code in (entry[1] for entry in _CORPS):
        cats = []
        for cat_index, cat in enumerate(menu.get(code, []), start=1):
            if not isinstance(cat, dict):
                continue
            cat_id = cat.get("id") or f"c{cat_index}"
            items = []
            for item_index, item in enumerate(cat.get("items", []), start=1):
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
            cats.append({
                "id": str(cat_id),
                "name": str(cat.get("name", "")).strip(),
                "visible": bool(cat.get("visible", True)),
                "items": items,
            })
        normalized[code] = cats
    return normalized


_CURRENT_MENU = _normalize_menu(_load_menu())


def _save_menu_normalized():
    """Сохраняет меню в файл (в нормализованном виде)."""
    _save_menu(_CURRENT_MENU)


def corpus_by_id(corpus_id):
    """Возвращает корпус (кортеж из _CORPS) по коду или None."""
    for entry in _CORPS:
        if entry[1] == corpus_id:
            return entry
    return None


def corpus_dict(entry):
    """Превращает кортеж корпуса в словарь для шаблона (с актуальными данными)."""
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


# Словами о каждом уровне загруженности (для легенды и подписей).
LOAD_DESCRIPTIONS = {
    "low": ("Свободно", "Можно спокойно поесть, без очереди."),
    "medium": ("Средняя загруженность", "Вероятно, придётся немного подождать."),
    "high": ("Высокая загруженность", "Большая очередь, лучше прийти позже."),
}

# Пароль от «режима работника» (хранится открытым текстом, чтобы было легко найти).
_ADMIN_PASSWORD = "2222"

# ===== CSRF-защита ======================================================
# На каждый мутирующий запрос (POST/PUT/PATCH/DELETE) клиент обязан прислать
# CSRF-токен (заголовок X-CSRF-Token). Это защищает от поддельных запросов
# со сторонних сайтов.


def get_csrf_token():
    """Возвращает CSRF-токен текущей сессии (создаёт, если его ещё нет)."""
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def _csrf_protect():
    """Проверяет CSRF-токен на мутирующем запросе. Возвращает ответ с ошибкой или None."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token") or ""
    token = session.get("_csrf_token")
    if not token or supplied != token:
        return jsonify({"error": "Неправильный или отсутствующий CSRF-токен"}), 403
    return None


@app.before_request
def csrf_guard():
    """CSRF-защита применяется ко всем мутирующим запросам."""
    return _csrf_protect()


# ===== Вспомогательные функции ==========================================

def role_info():
    """Возвращает (role, role_name): текущую роль и её название для шапки."""
    role = session.get("role", "guest")
    return role, "Гость" if role == "guest" else "Работник"


def _visible_menu(corpus_id, visible_only):
    """Меню корпуса.

    Для гостей (visible_only=True) скрытые категории пропускаются.
    Для работника возвращается всё меню, включая скрытое.
    """
    result = []
    for cat in _CURRENT_MENU.get(corpus_id, []):
        if visible_only and not cat["visible"]:
            continue
        result.append({
            "id": cat["id"],
            "name": cat["name"],
            "visible": cat["visible"],
            "items": [dict(item) for item in cat["items"]],
        })
    return result


def _require_admin():
    """Возвращает ответ с ошибкой, если текущий пользователь не работник, иначе None."""
    if session.get("role") != "admin":
        return jsonify({"error": "Нужен административный режим"}), 403
    return None


def _find_category(corpus_id, cat_id):
    """Находит категорию меню корпуса по id."""
    for cat in _CURRENT_MENU.get(corpus_id, []):
        if cat["id"] == cat_id:
            return cat
    return None


def _new_id(prefix):
    """Генерирует уникальный id категории или блюда для меню."""
    used = set()
    for cats in _CURRENT_MENU.values():
        for cat in cats:
            used.add(cat["id"])
            used.update(item["id"] for item in cat["items"])
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


# ===== Страницы (HTML отдаётся из templates/) ===========================

@app.route("/")
def index():
    """Главная страница — карта кампуса с метками загруженности."""
    role, role_name = role_info()
    corpuses = [corpus_dict(entry) for entry in _CORPS]
    return render_template(
        "index.html", corpuses=corpuses, role=role, role_name=role_name,
        csrf_token=get_csrf_token(),
    )


@app.route("/corpus/<corpus_id>")
def corpus(corpus_id):
    """Страница столовой — плашка статуса, оценка загруженности, меню."""
    entry = corpus_by_id(corpus_id)
    if entry is None:
        return "Корпус не найден", 404
    data = corpus_dict(entry)
    role, role_name = role_info()
    load_name, load_desc = LOAD_DESCRIPTIONS[data["load"]]
    return render_template(
        "corpus.html", corpus=data, role=role, role_name=role_name,
        load_name=load_name, load_desc=load_desc,
        csrf_token=get_csrf_token(),
    )


# ===== API (обмен данными со страницей) =================================

@app.route("/api/loads")
def api_loads():
    """Актуальная загруженность всех корпусов (для плавного обновления карты)."""
    return jsonify({code: _CURRENT_LOADS.get(code, default_load)
                    for _, code, _, default_load, _, _ in _CORPS})


@app.route("/corpus/<corpus_id>/report-load", methods=["POST"])
def report_load(corpus_id):
    """Сохраняет новую загруженность столовой, отправленную кнопкой на странице."""
    entry = corpus_by_id(corpus_id)
    if entry is None:
        return jsonify({"error": "Корпус не найден"}), 404
    payload = request.get_json(silent=True) or {}
    new_load = payload.get("load")
    if new_load not in ("low", "medium", "high"):
        return jsonify({"error": "Недопустимое значение load"}), 400

    # Простая защита от накрутки: не чаще одной оценки в 3 секунды с устройства.
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
    """Меняет текст расположения столовой (только для работника)."""
    err = _require_admin()
    if err:
        return err
    if corpus_by_id(corpus_id) is None:
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
    """Меню столовой в виде JSON для всплывающего окна."""
    entry = corpus_by_id(corpus_id)
    if entry is None:
        return jsonify({"error": "Корпус не найден"}), 404
    visible_only = session.get("role") != "admin"
    return jsonify(_visible_menu(corpus_id, visible_only))


# ===== Управление меню (только для работника) ===========================

@app.route("/corpus/<corpus_id>/menu/categories", methods=["POST"])
def add_category(corpus_id):
    """Добавляет категорию в меню столовой."""
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
    category = {"id": _new_id("cat"), "name": name, "visible": True, "items": []}
    _CURRENT_MENU.setdefault(corpus_id, []).append(category)
    _save_menu_normalized()
    return jsonify({"category": category})


@app.route("/corpus/<corpus_id>/menu/categories/<cat_id>", methods=["PUT", "DELETE", "PATCH"])
def manage_category(corpus_id, cat_id):
    """Изменение категории: PUT — название, PATCH — видимость, DELETE — удаление."""
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
        if "visible" in payload:
            cat["visible"] = bool(payload["visible"])
        _save_menu_normalized()
        return jsonify({"category": cat})
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Название категории не может быть пустым"}), 400
    cat["name"] = name
    _save_menu_normalized()
    return jsonify({"category": cat})


@app.route("/corpus/<corpus_id>/menu/items", methods=["POST"])
def add_item(corpus_id):
    """Добавляет блюдо в указанную категорию меню."""
    err = _require_admin()
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    cat = _find_category(corpus_id, (payload.get("category_id") or "").strip())
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
    item = {
        "id": _new_id("it"),
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
    """Изменение блюда: PUT — данные, PATCH — видимость, DELETE — удаление."""
    err = _require_admin()
    if err:
        return err
    if corpus_by_id(corpus_id) is None:
        return jsonify({"error": "Корпус не найден"}), 404
    for cat in _CURRENT_MENU.get(corpus_id, []):
        for item in cat["items"]:
            if item["id"] != item_id:
                continue
            if request.method == "DELETE":
                cat["items"] = [i for i in cat["items"] if i["id"] != item_id]
                _save_menu_normalized()
                return jsonify({"ok": True})
            payload = request.get_json(silent=True) or {}
            if request.method == "PATCH":
                if "visible" in payload:
                    item["visible"] = bool(payload["visible"])
                _save_menu_normalized()
                return jsonify({"item": item})
            # PUT — обновление полей блюда
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


# ===== Вход и выход из режима работника =================================

@app.route("/login", methods=["POST"])
def login():
    """Вход в режим работника — проверяет пароль, переданный плашкой на главной."""
    payload = request.get_json(silent=True) or request.form
    password = (payload.get("password") or "").strip()
    if password == _ADMIN_PASSWORD:
        session["role"] = "admin"
        return jsonify({"ok": True})
    return jsonify({"error": "Неверный пароль"}), 401


@app.route("/logout", methods=["POST"])
def logout():
    """Выход из режима работника и возврат на главную."""
    session["role"] = "guest"
    return redirect(url_for("index"))


if __name__ == "__main__":
    # Режим отладки включается только через FLASK_DEBUG=1 (для разработки).
    debug = os.environ.get("FLASK_DEBUG", "").strip().lower() in ("1", "true", "yes")
    port = int(os.environ.get("PORT", 80))
    app.run(host="0.0.0.0", port=port, debug=debug)