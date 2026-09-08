# -*- coding: utf-8 -*-
"""
УрФУ Столовая — сайт загруженности столовых.

Структура проекта (backend/):
  run.py            — этот файл: сервер и вся логика на Python
  templates/        — HTML-страницы (index.html, corpus.html)
  static/           — картинки и скрипты (css внутри шаблонов, js в static/js)
  data/             — меню и расположения (JSON), голоса и votes.db (SQLite)

Запуск:  python run.py
Открыть: http://127.0.0.1:5000/
"""
import json
import os
import secrets
import threading
import time
from datetime import datetime

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

# Модуль голосования (голоса в SQLite, расчёт статуса) — см. vote.py.
from vote import cast_vote, cached_status, list_recent_votes, vote_bp

# ===== Папки проекта =====================================================
# Все папки задаём явно (относительно этого файла), чтобы сервер работал
# независимо от того, из какой папки его запустили.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_BASE_DIR, "data")

# Секретный ключ нужен для сессий (кто сейчас «работник», CSRF-токен и т.д.).
# Берётся из переменной окружения SECRET_KEY, а если её нет — из локального
# файла .secret_key (создаётся один раз и не попадает в git, см. .gitignore).
# Так ключ не «светится» в коде и остаётся стабильным между перезапусками.
_SECRET_FILE = os.path.join(_DATA_DIR, ".secret_key")


def _load_secret_key():
    from_env = os.environ.get("SECRET_KEY")
    if from_env:
        return from_env
    try:
        with open(_SECRET_FILE, "r", encoding="utf-8") as f:
            key = f.read().strip()
        if key:
            return key
    except (OSError, ValueError):
        pass
    key = secrets.token_hex(32)
    try:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_SECRET_FILE, "w", encoding="utf-8") as f:
            f.write(key)
    except OSError:
        pass
    return key


app = Flask(
    __name__,
    template_folder=os.path.join(_BASE_DIR, "templates"),
    static_folder=os.path.join(_BASE_DIR, "static"),
)

app.secret_key = _load_secret_key()

# Регистрируем маршруты голосования (/vote и /status/<id>) из vote.py.
app.register_blueprint(vote_bp)

# ===== Данные о корпусах ================================================
# Статика (имена, расположение, позиции меток) — здесь (список _CORPS ниже).
# Расположение столовых и меню — в JSON-файлах папки data/ (меняются без
# правки кода). Загруженность считается по голосам из votes.db (см. vote.py).


def _make_pins(corpus_code):
    """Имена пин-картинок для метки корпуса: {low, medium, high -> файл}."""
    return {level: f"pin-{level}-{corpus_code}.png" for level in ("low", "medium", "high")}


# (имя, код, расположение столовой, загрузка по умолчанию, x метки, y метки)
_CORPS = [
    ("ИРИТ-РТФ", "irit", "2 этаж, крыло Б", "low", 46, 23),
    ("ИнЭУ",     "ineu", "1 этаж, справа от входа", "medium", 82, 13),
    ("ОЦК",      "cimt", "2 этаж, атриум", "high", 17, 70),
]

_LOCATIONS_FILE = os.path.join(_DATA_DIR, "locations.json")
_MENU_FILE = os.path.join(_DATA_DIR, "menu.json")

# При старте гарантируем, что папка с данными существует.
os.makedirs(_DATA_DIR, exist_ok=True)

# Блокировка нужна, чтобы два запроса не записывали JSON-файл одновременно.
_IO_LOCK = threading.Lock()


# Значение по умолчанию для расположений — fallback, если JSON-файл битый.
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


# Актуальные расположения столовых, загруженные при старте.
# (Загруженность хранится в голосах SQLite — см. module vote.py.)
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


# ===== Гостевые пометки «блюдо отсутствует» =============================
# Гости могут отмечать блюда как отсутствующие (например, когда админ не
# успел обновить меню). Такая пометка живёт сутки, выглядит иначе, чем
# «Нет в наличии» от работника, и её может отменить любой гость или
# работник. Храним их отдельно от menu.json, чтобы не портить меню.

_GUEST_REPORTS_FILE = os.path.join(_DATA_DIR, "guest_reports.json")
_GUEST_REPORT_TTL = 24 * 60 * 60  # сутки


def _load_guest_reports():
    """Читает пометки гостей: {код корпуса: {id блюда: время(timestamp)}}."""
    defaults = {code: {} for name, code, loc, load, x, y in _CORPS}
    try:
        with open(_GUEST_REPORTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {code: data.get(code, {}) for code, _ in defaults.items()}
    except (OSError, ValueError):
        return defaults


_GUEST_REPORTS = _load_guest_reports()
_last_guest_purge = time.time()

# Словарь для быстрого поиска корпуса по коду (вместо линейного поиска по списку).
_CORPS_BY_ID = {entry[1]: entry for entry in _CORPS}


def _save_guest_reports():
    """Сохраняет пометки гостей в JSON-файл."""
    _save_json(_GUEST_REPORTS_FILE, _GUEST_REPORTS)


def _purge_expired_guest_reports(now=None):
    """Удаляет пометки гостей старше суток и сохраняет изменения.

    Вызывается не при каждом запросе, а не чаще раза в 60 секунд,
    чтобы не тратить время на чтение/запись JSON.
    """
    global _last_guest_purge
    now = now if now is not None else time.time()
    if now - _last_guest_purge < 60:
        return
    _last_guest_purge = now
    changed = False
    for code, reports in _GUEST_REPORTS.items():
        fresh = {item_id: ts for item_id, ts in reports.items()
                 if now - ts < _GUEST_REPORT_TTL}
        if len(fresh) != len(reports):
            _GUEST_REPORTS[code] = fresh
            changed = True
    if changed:
        _save_guest_reports()


def _guest_reported_items(corpus_id):
    """Множество id блюд корпуса, помеченных гостями."""
    _purge_expired_guest_reports()
    return set(_GUEST_REPORTS.get(corpus_id, {}).keys())


def corpus_by_id(corpus_id):
    """Возвращает корпус (кортеж из _CORPS) по коду или None."""
    return _CORPS_BY_ID.get(corpus_id)


def corpus_dict(entry):
    """Превращает кортеж корпуса в словарь для шаблона (с актуальными данными)."""
    name, code, canteen_location, default_load, x, y = entry
    stat = cached_status(code)
    nodata = stat["status"] == "NO_DATA"
    return {
        "id": code,
        "name": name,
        "canteen_location": _CURRENT_LOCATIONS.get(code, canteen_location),
        # Если голосов мало (NO_DATA) — показываем уровень по умолчанию.
        "load": default_load if nodata else stat["status"],
        "pin_x": x,
        "pin_y": y,
        "pin_files": _make_pins(code),
        "confidence": stat["confidence"],
        "votes": stat["total_votes"],
        "voters": stat["voters"],
        "status_nodata": nodata,
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
    reported = _guest_reported_items(corpus_id)
    result = []
    for cat in _CURRENT_MENU.get(corpus_id, []):
        if visible_only and not cat["visible"]:
            continue
        result.append({
            "id": cat["id"],
            "name": cat["name"],
            "visible": cat["visible"],
            "items": [dict(item, guest_missing=(item["id"] in reported))
                      for item in cat["items"]],
        })
    return result


def _find_item(corpus_id, item_id):
    """Ищет блюдо в меню корпуса по id (или None)."""
    for cat in _CURRENT_MENU.get(corpus_id, []):
        for item in cat["items"]:
            if item["id"] == item_id:
                return item
    return None


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


@app.route("/journal")
def journal():
    """Журнал событий (только для работника): последние голоса с метками времени."""
    err = _require_admin()
    if err:
        return err

    name_by_code = {entry[1]: entry[0] for entry in _CORPS}
    status_text = {"low": "Свободно", "medium": "Средне", "high": "Много народу"}
    events = []
    for row in list_recent_votes(50):
        events.append({
            # Метка времени в удобном виде (в базе хранится в секундах).
            "time": datetime.fromtimestamp(row["timestamp"]).strftime("%H:%M:%S %d.%m.%Y"),
            "cafeteria": name_by_code.get(row["cafeteria_id"], row["cafeteria_id"]),
            # status_key нужен для цветной точки; status — русское название уровня.
            "status_key": row["status"],
            "status": status_text.get(row["status"], row["status"]),
            # Показываем только первые символы анонимного id, чтобы не раскрывать посетителей.
            "session": (row["session_id"] or "")[:6] + "…",
        })

    role, role_name = role_info()
    return render_template(
        "journal.html", events=events, role=role, role_name=role_name,
        csrf_token=get_csrf_token(),
    )


# ===== API (обмен данными со страницей) =================================

@app.route("/api/loads")
def api_loads():
    """Загруженность всех корпусов для карты на главной (уровень + метрики)."""
    result = {}
    for entry in _CORPS:
        name, code, canteen_location, default_load, x, y = entry
        stat = cached_status(code)
        nodata = stat["status"] == "NO_DATA"
        result[code] = {
            "load": default_load if nodata else stat["status"],
            "confidence": stat["confidence"],
            "votes": stat["total_votes"],
            "voters": stat["voters"],
            "nodata": nodata,
        }
    return jsonify(result)


@app.route("/corpus/<corpus_id>/report-load", methods=["POST"])
def report_load(corpus_id):
    """Сохраняет голос за загруженность (адрес, который зовут кнопки на странице)."""
    entry = corpus_by_id(corpus_id)
    if entry is None:
        return jsonify({"error": "Корпус не найден"}), 404
    payload = request.get_json(silent=True) or {}
    new_load = payload.get("load")
    if new_load not in ("low", "medium", "high"):
        return jsonify({"error": "Недопустимое значение load"}), 400

    # Кладём голос в базу; cast_vote сам проверит «не чаще раза в минуту».
    result, code = cast_vote(corpus_id, new_load)
    if code != 200:
        return jsonify(result), code

    # Ответ отдаём в прежнем виде, чтобы страница умела показывать сообщения.
    nodata = result["status"] == "NO_DATA"
    level = entry[3] if nodata else result["status"]  # при NO_DATA — уровень по умолчанию
    load_name, load_desc = LOAD_DESCRIPTIONS[level]
    result["load"] = level
    result["load_name"] = load_name
    result["load_desc"] = load_desc
    result["nodata"] = nodata
    return jsonify(result)


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


@app.route("/corpus/<corpus_id>/menu/items/<item_id>/guest-missing", methods=["POST"])
def toggle_guest_missing(corpus_id, item_id):
    """Отметить/снять пометку «блюдо отсутствует» (доступно гостям).

    Пометка гостя живёт сутки; её может отменить любой гость, а работник —
    кнопкой «Сбросить пометку гостей» в админ-режиме.
    """
    if corpus_by_id(corpus_id) is None:
        return jsonify({"error": "Корпус не найден"}), 404
    if _find_item(corpus_id, item_id) is None:
        return jsonify({"error": "Блюдо не найдено"}), 404

    payload = request.get_json(silent=True) or {}
    mark = bool(payload.get("mark", True))

    _purge_expired_guest_reports()
    reports = _GUEST_REPORTS.setdefault(corpus_id, {})
    if mark:
        reports[item_id] = time.time()
    else:
        reports.pop(item_id, None)
    _save_guest_reports()
    return jsonify({"guest_missing": item_id in reports})


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