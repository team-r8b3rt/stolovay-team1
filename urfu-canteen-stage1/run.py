"""
Точка входа в приложение.
Запуск: python run.py
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    # debug=True — удобно на время разработки, выключить перед боевым запуском
    app.run(debug=True)
