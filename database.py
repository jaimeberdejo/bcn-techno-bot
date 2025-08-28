# database.py
import sqlite3

def setup_database():
    conn = sqlite3.connect('techno_events.db')
    cursor = conn.cursor()

    # --- TABLA DE EVENTOS ACTUALIZADA ---
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name TEXT NOT NULL,
            club_name TEXT,
            event_date DATE NOT NULL,
            start_time TEXT,          -- NUEVO: Para la hora de inicio
            end_time TEXT,            -- NUEVO: Para la hora de fin
            artists TEXT,
            attending_count INTEGER,  -- NUEVO: Para el número de asistentes
            buy_link TEXT,
            source_link TEXT UNIQUE NOT NULL,
            flyer_image TEXT,
            notified INTEGER DEFAULT 0,
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Las tablas users y alerts no necesitan cambios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users ( chat_id INTEGER PRIMARY KEY )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            alert_type TEXT NOT NULL,
            alert_value TEXT NOT NULL,
            FOREIGN KEY(chat_id) REFERENCES users(chat_id),
            UNIQUE(chat_id, alert_type, alert_value)
        )
    ''')

    conn.commit()
    conn.close()
    print("Base de datos (enriquecida) configurada y lista.")

# --- EL RESTO DE FUNCIONES NO NECESITAN CAMBIOS ---
# Las funciones como get_upcoming_events y search_events usan "SELECT *"
# por lo que automáticamente incluirán las nuevas columnas.

def get_upcoming_events(limit=5, offset=0):
    conn = sqlite3.connect('techno_events.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events WHERE event_date >= date('now', 'localtime') ORDER BY event_date ASC, start_time ASC LIMIT ? OFFSET ?", (limit, offset))
    events = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) FROM events WHERE event_date >= date('now', 'localtime')")
    total_events = cursor.fetchone()[0]
    conn.close()
    return events, total_events

def search_events(query, search_by, limit=5, offset=0):
    conn = sqlite3.connect('techno_events.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    search_query = f'%{query}%'
    if search_by not in ['artists', 'club_name']: return [], 0
    count_sql = f"SELECT COUNT(*) FROM events WHERE {search_by} LIKE ? AND event_date >= date('now', 'localtime')"
    cursor.execute(count_sql, (search_query,))
    total_events = cursor.fetchone()[0]
    paginated_sql = f"SELECT * FROM events WHERE {search_by} LIKE ? AND event_date >= date('now', 'localtime') ORDER BY event_date ASC LIMIT ? OFFSET ?"
    cursor.execute(paginated_sql, (search_query, limit, offset))
    events = cursor.fetchall()
    conn.close()
    return events, total_events

def search_events_by_date(start_date_str, end_date_str, limit=5, offset=0):
    """
    Busca eventos en la base de datos dentro de un rango de fechas, con paginación.
    - start_date_str: Fecha de inicio en formato 'YYYY-MM-DD'.
    - end_date_str: Fecha de fin en formato 'YYYY-MM-DD'.
    """
    conn = sqlite3.connect('techno_events.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Contamos el total de resultados para la paginación
    cursor.execute("""
        SELECT COUNT(*) FROM events 
        WHERE event_date BETWEEN ? AND ?
    """, (start_date_str, end_date_str))
    total_events = cursor.fetchone()[0]

    # Obtenemos los eventos de la página actual
    cursor.execute("""
        SELECT * FROM events 
        WHERE event_date BETWEEN ? AND ?
        ORDER BY event_date ASC, start_time ASC 
        LIMIT ? OFFSET ?
    """, (start_date_str, end_date_str, limit, offset))
    events = cursor.fetchall()
    
    conn.close()
    return events, total_events

def get_unique_clubs(limit=20, offset=0):
    """Obtiene una lista paginada de nombres de clubs únicos y ordenados."""
    conn = sqlite3.connect('techno_events.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Contar el total de clubs únicos
    cursor.execute("""
        SELECT COUNT(DISTINCT club_name) FROM events
        WHERE event_date >= date('now', 'localtime')
    """)
    total_clubs = cursor.fetchone()[0]

    # Obtener la lista paginada de clubs
    cursor.execute("""
        SELECT DISTINCT club_name FROM events
        WHERE event_date >= date('now', 'localtime')
        ORDER BY club_name ASC
        LIMIT ? OFFSET ?
    """, (limit, offset))
    
    # Extraemos solo el nombre de cada fila
    clubs = [row['club_name'] for row in cursor.fetchall()]
    
    conn.close()
    return clubs, total_clubs

def get_unique_artists():
    """
    Obtiene una lista completa de todos los artistas únicos y ordenados.
    El procesamiento se hace en Python debido a que los artistas están en un solo campo de texto.
    """
    conn = sqlite3.connect('techno_events.db')
    cursor = conn.cursor()

    # Obtenemos todas las cadenas de artistas de los próximos eventos
    cursor.execute("""
        SELECT artists FROM events
        WHERE event_date >= date('now', 'localtime')
    """)
    
    all_artists_raw = cursor.fetchall()
    conn.close()

    unique_artists = set()
    for artists_tuple in all_artists_raw:
        # artists_tuple es ('Artista A, Artista B',)
        artists_string = artists_tuple[0]
        # Dividimos la cadena por comas y limpiamos los espacios
        artists_list = [artist.strip() for artist in artists_string.split(',')]
        for artist in artists_list:
            if artist and artist.lower() != "artistas por confirmar":
                unique_artists.add(artist)

    # Devolvemos la lista ordenada alfabéticamente
    return sorted(list(unique_artists), key=str.lower)

# (Aquí irían el resto de funciones de alertas, que no cambian)
def add_user_if_not_exists(chat_id):
    conn = sqlite3.connect('techno_events.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (chat_id) VALUES (?)", (chat_id,))
    conn.commit()
    conn.close()

def add_alert(chat_id, alert_type, alert_value):
    conn = sqlite3.connect('techno_events.db')
    cursor = conn.cursor()
    add_user_if_not_exists(chat_id)
    cursor.execute("INSERT OR IGNORE INTO alerts (chat_id, alert_type, alert_value) VALUES (?, ?, ?)", 
                   (chat_id, alert_type, alert_value.lower()))
    conn.commit()
    conn.close()

def get_user_alerts(chat_id):
    conn = sqlite3.connect('techno_events.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, alert_type, alert_value FROM alerts WHERE chat_id = ?", (chat_id,))
    alerts = cursor.fetchall()
    conn.close()
    return alerts

def delete_alert(alert_id):
    conn = sqlite3.connect('techno_events.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()

def find_users_for_new_event(event):
    conn = sqlite3.connect('techno_events.db')
    cursor = conn.cursor()
    chat_ids = set()
    cursor.execute("SELECT chat_id FROM alerts WHERE alert_type = 'club' AND ? LIKE '%' || alert_value || '%'", (event['club_name'].lower(),))
    for row in cursor.fetchall():
        chat_ids.add(row[0])
    artists = [artist.strip().lower() for artist in event['artists'].split(',')]
    for artist in artists:
        if artist:
            cursor.execute("SELECT chat_id FROM alerts WHERE alert_type = 'artist' AND ? LIKE '%' || alert_value || '%'", (artist,))
            for row in cursor.fetchall():
                chat_ids.add(row[0])
    conn.close()
    return list(chat_ids)


if __name__ == '__main__':
    setup_database()