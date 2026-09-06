"""
Фабрика Flask-приложения.
Здесь всё максимально просто, чтобы новичку было легко разобраться.
"""
from flask import Flask, session


def create_app():
    app = Flask(__name__)

    # Секретный ключ нужен для сессий (session['role'] и т.п.)
    # TODO: перед боевым запуском вынести в переменную окружения
    app.secret_key = "dev-secret-key-change-me"

    from .routes import bp as main_blueprint
    app.register_blueprint(main_blueprint)

    # Передаём роль пользователя во все шаблоны
    @app.context_processor
    def inject_role():
        # TODO: заменить на настоящую проверку пароля (Этап 1 сохранил заглушку)
        role = session.get("role", "guest")
        return {
            "role": role,
            "role_name": "Гость" if role == "guest" else "Админ",
        }

    return app
