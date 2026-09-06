"""
Все маршруты (роуты) сайта.
Этап 1: главная страница, вход/выход админа (заглушка), страница корпуса (заглушка).
"""
import json
import os

from flask import Blueprint, render_template, redirect, url_for, session

bp = Blueprint("main", __name__)

# Путь к данным о корпусах
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CORPUSES_FILE = os.path.join(DATA_DIR, "corpuses.json")

# Соответствие уровня загруженности имени файла-капельки
LOAD_TO_PIN = {
    "low": "pin-green.svg",
    "medium": "pin-yellow.svg",
    "high": "pin-red.svg",
}


def load_corpuses():
    """Читает corpuses.json и возвращает список корпусов."""
    with open(CORPUSES_FILE, encoding="utf-8") as f:
        return json.load(f)


@bp.route("/")
def index():
    corpuses = load_corpuses()
    # Добавляем каждому корпусу имя файла капельки по его загруженности
    for corpus in corpuses:
        corpus["pin"] = LOAD_TO_PIN.get(corpus.get("load"), "pin-green.svg")
    return render_template("index.html", corpuses=corpuses)


@bp.route("/login", methods=["POST"])
def login():
    # TODO: заменить на настоящую проверку пароля
    session["role"] = "admin"
    return redirect(url_for("main.index"))


@bp.route("/logout", methods=["POST"])
def logout():
    session["role"] = "guest"
    return redirect(url_for("main.index"))


@bp.route("/corpus/<corpus_id>")
def corpus(corpus_id):
    corpuses = load_corpuses()
    # Ищем корпус по id, если нет — отдадим None (в шаблоне обработаем)
    corpus = next((c for c in corpuses if c["id"] == corpus_id), None)
    # Этап 2: здесь будет реальная страница корпуса, пока — заглушка
    return render_template("corpus_stub.html", corpus=corpus)
