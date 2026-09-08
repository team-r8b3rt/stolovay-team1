# -*- coding: utf-8 -*-
"""
Модуль голосования за загруженность столовой.

Как это работает.
  - Каждый гость голосует за столовую: low / medium / high.
  - Голоса хранятся в базе SQLite (файл votes.db в папке data/).
  - Итоговый статус считает compute_status(): берутся голоса за последние
    10 минут, каждому присваивается вес (свежий голос — 3, старый — 1),
    считается взвешенное среднее и переводится в уровень по порогам.
  - Один посетитель может голосовать за одну столовую не чаще раза в минуту,
    а повторный голос обновляет его старое значение (у человека — одно мнение),
    а не добавляется новым.

Как подключить в run.py (всего две строки):
    from vote import vote_bp
    app.register_blueprint(vote_bp)
"""
import os
import secrets
import sqlite3
import threading
import time

from flask import Blueprint, jsonify, request, session

# ===== Настройки ===========================================================

# Номера уровней: low=1, medium=2, high=3 (нужны для взвешенного среднего).
LEVEL_SCORE = {"low": 1, "medium": 2, "high": 3}

# Голос «живёт» 10 минут — более старые в расчёт не берутся.
WINDOW_SECONDS = 10 * 60

# Голосовать за одну столовую можно не чаще, чем раз в минуту.
VOTE_GAP_SECONDS = 1 * 60

# Вес голоса по возрасту: до 3 минут — свежий (вес больше), иначе старый.
FRESH_SECONDS = 3 * 60
FRESH_WEIGHT = 3
OLD_WEIGHT = 1

# Меньше 2 голосов — данных мало, показываем NO_DATA (статус появляется
# уже при двух голосах, чтобы маркеры на карте не держались серыми).
MIN_VOTES = 2

# Кеш для GET /status: храним посчитанный статус не дольше 10 секунд,
# чтобы ответы были быстрыми, но данные — свежими.
CACHE_SECONDS = 10

# Папка с данными проекта (там же живут locations.json и menu.json).
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_DB_PATH = os.path.join(_DATA_DIR, "votes.db")

# ===== Blueprint ===========================================================

vote_bp = Blueprint("votes", __name__)

# Кеш: cafeteria_id -> (когда посчитано, результат).
_status_cache = {}
_status_lock = threading.Lock()


def _connect():
    """Открывает соединение с базой (новое на каждый запрос — так проще)."""
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Создаёт таблицу голосов, если её ещё нет. Вызывается при импорте."""
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cafeteria_id TEXT NOT NULL,
                status TEXT NOT NULL,
                session_id TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
        """)
        # Индекс ускоряет выборку «последние 10 минут для конкретной столовой».
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_votes_cafeteria "
            "ON votes (cafeteria_id, timestamp)"
        )
        conn.commit()
    finally:
        conn.close()


def _uid():
    """Анонимный id посетителя из сессии (куки). Создаётся при первом голосе."""
    uid = session.get("_vote_uid")
    if not uid:
        uid = secrets.token_hex(8)
        session["_vote_uid"] = uid
    return uid


def _invalidate_cache(cafeteria_id):
    """Сбрасывает кеш статуса после нового голоса."""
    with _status_lock:
        _status_cache.pop(cafeteria_id, None)


def _cleanup_old(conn, now):
    """Удаляет давние голоса, чтобы таблица не росла бесконечно."""
    conn.execute("DELETE FROM votes WHERE timestamp < ?", (now - 2 * WINDOW_SECONDS,))


def _recent_votes(cafeteria_id, now):
    """Голоса за последние 10 минут для этой столовой (свежие сверху)."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT status, timestamp, session_id FROM votes "
            "WHERE cafeteria_id = ? AND timestamp >= ? "
            "ORDER BY timestamp DESC",
            (cafeteria_id, now - WINDOW_SECONDS),
        ).fetchall()
        return rows
    finally:
        conn.close()


def list_recent_votes(limit=50):
    """Свежие голоса для журнала событий: от новых к старым, не больше limit."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, cafeteria_id, status, session_id, timestamp "
            "FROM votes ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return rows
    finally:
        conn.close()


def compute_status(cafeteria_id, now=None):
    """
    Считает текущий статус столовой из всех голосов.

    Возвращает словарь: {status, confidence, total_votes, voters}.
    Параметр now можно передать при тестах, чтобы подделать время.
    """
    if now is None:
        now = time.time()

    votes = _recent_votes(cafeteria_id, now)
    total = len(votes)
    voters = len({row["session_id"] for row in votes})

    # Меньше 2 голосов — слишком мало мнений, отдаём «нет данных».
    if total < MIN_VOTES:
        return {
            "status": "NO_DATA",
            "confidence": 0.0,
            "total_votes": total,
            "voters": voters,
        }

    score_sum = 0.0      # Σ(вес × число уровня)
    weight_sum = 0.0     # Σ весов
    weight_by_status = {"low": 0.0, "medium": 0.0, "high": 0.0}

    for row in votes:
        age = now - row["timestamp"]
        weight = FRESH_WEIGHT if age <= FRESH_SECONDS else OLD_WEIGHT
        score = LEVEL_SCORE[row["status"]]
        score_sum += weight * score
        weight_sum += weight
        weight_by_status[row["status"]] += weight

    average = score_sum / weight_sum

    # Переводим взвешенное среднее в уровень.
    if average < 1.5:
        status = "low"
    elif average < 2.5:
        status = "medium"
    else:
        status = "high"

    # Доверие = доля веса голосов, совпавших с итоговым уровнем.
    confidence = round(weight_by_status[status] / weight_sum, 2)

    # Обеденный бонус: в часы пик (12:00-14:00) доверие чуть выше, но не больше 1.
    if 12 <= time.localtime(now).tm_hour < 14:
        confidence = round(min(confidence + 0.10, 1.0), 2)

    return {
        "status": status,
        "confidence": confidence,
        "total_votes": total,
        "voters": voters,
    }


def cast_vote(cafeteria_id, status, now=None):
    """
    Сохраняет голос и сразу возвращает свежий статус.

    У одного посетителя за столовую хранится один голос: если он уже есть,
    повторный голос не добавляет новую запись, а обновляет старую
    (значение уровня и время — голос «омолаживается»).

    Возвращает пару (json-словарь, http-код).
    Если этот посетитель уже голосовал за эту столовую последнюю минуту —
    вернёт (ошибка) 429 и ничего не сохранит.
    """
    now = now if now is not None else time.time()
    voter_id = _uid()

    conn = _connect()
    try:
        # Проверка «не чаще раза в минуту» и поиск существующего голоса.
        row = conn.execute(
            "SELECT id, timestamp FROM votes "
            "WHERE cafeteria_id = ? AND session_id = ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (cafeteria_id, voter_id),
        ).fetchone()

        if row is not None and now - row["timestamp"] < VOTE_GAP_SECONDS:
            return (
                {"error": "Вы уже голосовали за эту столовую. Подождите минуту."},
                429,
            )

        # Сохраняем голос и заодно чистим совсем старые записи.
        _cleanup_old(conn, now)
        if row is None:
            conn.execute(
                "INSERT INTO votes (cafeteria_id, status, session_id, timestamp) "
                "VALUES (?, ?, ?, ?)",
                (cafeteria_id, status, voter_id, now),
            )
        else:
            conn.execute(
                "UPDATE votes SET status = ?, timestamp = ? WHERE id = ?",
                (status, now, row["id"]),
            )
        conn.commit()
    finally:
        conn.close()

    _invalidate_cache(cafeteria_id)
    return compute_status(cafeteria_id, now), 200


# ===== Маршруты ============================================================

@vote_bp.route("/vote", methods=["POST"])
def vote():
    """Обрабатывает голос: JSON-запрос {cafeteria_id, status}."""
    payload = request.get_json(silent=True) or {}
    cafeteria_id = (payload.get("cafeteria_id") or "").strip()
    status = (payload.get("status") or "").strip()

    if not cafeteria_id:
        return jsonify({"error": "Не указана столовая"}), 400
    if status not in LEVEL_SCORE:
        return jsonify({"error": "Недопустимое значение status"}), 400

    result, code = cast_vote(cafeteria_id, status)
    return jsonify(result), code


@vote_bp.route("/status/<cafeteria_id>")
def status(cafeteria_id):
    """Текущий статус столовой с кешированием на 10 секунд (GET /status/<id>)."""
    return jsonify(cached_status(cafeteria_id))


def cached_status(cafeteria_id, now=None):
    """Статус столовой, взятый из кеша (считается не чаще раза в CACHE_SECONDS).

    Общая функция для /status и карты на главной (/api/loads): они делят один
    кеш и одну блокировку, поэтому карта не нагружает сервер лишними
    пересчётами.
    """
    if now is None:
        now = time.time()

    with _status_lock:
        cached = _status_cache.get(cafeteria_id)
        if cached is not None and now - cached[0] < CACHE_SECONDS:
            return cached[1]

    result = compute_status(cafeteria_id, now)

    with _status_lock:
        _status_cache[cafeteria_id] = (now, result)
    return result


init_db()