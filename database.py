# database.py
import sqlite3

def setup_database():
    conn = sqlite3.connect('techno_events.db')
    cursor = conn.cursor()

    # Tabla para guardar los eventos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name TEXT,
            club_name TEXT,
            event_date TEXT,
            artists TEXT,
            price TEXT,
            buy_link TEXT,
            source_link TEXT UNIQUE, -- El link original para evitar duplicados
            flyer_image TEXT,
            notified INTEGER DEFAULT 0 -- 0 para no notificado, 1 para ya notificado
        )
    ''')

    # Tabla para guardar usuarios y sus preferencias
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            notification_frequency TEXT DEFAULT 'instant' -- 'instant' o 'daily'
        )
    ''')

    # Tabla para las alertas personalizadas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            alert_type TEXT, -- 'artist' o 'club'
            alert_value TEXT,
            FOREIGN KEY(chat_id) REFERENCES users(chat_id)
        )
    ''')

    conn.commit()
    conn.close()
    print("Base de datos configurada correctamente.")

if __name__ == '__main__':
    setup_database()