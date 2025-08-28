# -*- coding: utf-8 -*-

"""
Módulo de Base de Datos para BCN Techno Radar Bot.

Este módulo gestiona todas las interacciones con la base de datos SQLite,
incluyendo la configuración inicial de las tablas y las operaciones CRUD
(Crear, Leer, Actualizar, Borrar) para eventos, usuarios y alertas.
"""

import sqlite3
from typing import List, Tuple, Dict, Any

# --- CONFIGURACIÓN Y CONEXIÓN ---

DB_NAME = 'techno_events.db'

def _get_db_connection() -> sqlite3.Connection:
    """
    Establece y devuelve una conexión a la base de datos.
    Configura row_factory para que las filas se puedan acceder como diccionarios.
    
    Returns:
        sqlite3.Connection: Objeto de conexión a la base de datos.
    """
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # Permite acceder a las columnas por nombre
    return conn

# --- FUNCIONES DE CONFIGURACIÓN ---

def setup_database() -> None:
    """
    Crea las tablas necesarias (events, users, alerts) en la base de datos si no existen.
    Esta función se ejecuta una vez para inicializar el esquema de la BD.
    """
    print("Configurando la base de datos...")
    with _get_db_connection() as conn:
        cursor = conn.cursor()

        # Tabla de eventos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_name TEXT NOT NULL,
                club_name TEXT,
                event_date DATE NOT NULL,
                start_time TEXT,
                end_time TEXT,
                artists TEXT,
                attending_count INTEGER,
                buy_link TEXT,
                source_link TEXT UNIQUE NOT NULL,
                flyer_image TEXT,
                notified INTEGER DEFAULT 0,
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tabla de usuarios
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY
            )
        """)

        # Tabla de alertas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                alert_type TEXT NOT NULL,       -- 'artist' o 'club'
                alert_value TEXT NOT NULL,
                FOREIGN KEY(chat_id) REFERENCES users(chat_id) ON DELETE CASCADE,
                UNIQUE(chat_id, alert_type, alert_value)
            )
        """)
        conn.commit()
    print("Base de datos configurada y lista.")

# --- FUNCIONES DE GESTIÓN DE EVENTOS ---

def get_upcoming_events(limit: int = 5, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    """
    Obtiene una lista paginada de eventos futuros.

    Args:
        limit (int): Número máximo de eventos a devolver.
        offset (int): Desplazamiento para la paginación.

    Returns:
        Tuple[List[Dict[str, Any]], int]: Una tupla con la lista de eventos y el número total de eventos futuros.
    """
    with _get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Obtener eventos paginados
        query = """
            SELECT * FROM events 
            WHERE event_date >= date('now', 'localtime') 
            ORDER BY event_date ASC, start_time ASC 
            LIMIT ? OFFSET ?
        """
        cursor.execute(query, (limit, offset))
        events = [dict(row) for row in cursor.fetchall()]

        # Contar el total de eventos
        count_query = "SELECT COUNT(*) FROM events WHERE event_date >= date('now', 'localtime')"
        total_events = cursor.execute(count_query).fetchone()[0]
        
        return events, total_events

def search_events(query: str, search_by: str, limit: int = 5, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    """
    Busca eventos futuros por artista o club.

    Args:
        query (str): El término de búsqueda.
        search_by (str): El campo por el cual buscar ('artists' o 'club_name').
        limit (int): Número máximo de eventos a devolver.
        offset (int): Desplazamiento para la paginación.

    Returns:
        Tuple[List[Dict[str, Any]], int]: Tupla con la lista de eventos encontrados y el total.
    """
    # Whitelist para evitar inyección SQL en el nombre de la columna. ¡Muy importante!
    if search_by not in ['artists', 'club_name']:
        return [], 0

    search_term = f'%{query}%'
    
    with _get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Contar total de resultados
        count_sql = f"""
            SELECT COUNT(*) FROM events 
            WHERE {search_by} LIKE ? AND event_date >= date('now', 'localtime')
        """
        total_events = cursor.execute(count_sql, (search_term,)).fetchone()[0]

        # Obtener resultados paginados
        paginated_sql = f"""
            SELECT * FROM events 
            WHERE {search_by} LIKE ? AND event_date >= date('now', 'localtime') 
            ORDER BY event_date ASC, start_time ASC
            LIMIT ? OFFSET ?
        """
        cursor.execute(paginated_sql, (search_term, limit, offset))
        events = [dict(row) for row in cursor.fetchall()]

        return events, total_events

def search_events_by_date(start_date: str, end_date: str, limit: int = 5, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
    """
    Busca eventos en un rango de fechas específico.

    Args:
        start_date (str): Fecha de inicio en formato 'YYYY-MM-DD'.
        end_date (str): Fecha de fin en formato 'YYYY-MM-DD'.
        limit (int): Número máximo de eventos a devolver.
        offset (int): Desplazamiento para la paginación.

    Returns:
        Tuple[List[Dict[str, Any]], int]: Tupla con la lista de eventos encontrados y el total.
    """
    with _get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Contar total de resultados
        count_query = "SELECT COUNT(*) FROM events WHERE event_date BETWEEN ? AND ?"
        total_events = cursor.execute(count_query, (start_date, end_date)).fetchone()[0]
        
        # Obtener resultados paginados
        query = """
            SELECT * FROM events 
            WHERE event_date BETWEEN ? AND ?
            ORDER BY event_date ASC, start_time ASC 
            LIMIT ? OFFSET ?
        """
        cursor.execute(query, (start_date, end_date, limit, offset))
        events = [dict(row) for row in cursor.fetchall()]

        return events, total_events

def get_unnotified_events() -> List[Dict[str, Any]]:
    """
    Obtiene todos los eventos que aún no han sido notificados.

    Returns:
        List[Dict[str, Any]]: Lista de eventos no notificados.
    """
    with _get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events WHERE notified = 0")
        events = [dict(row) for row in cursor.fetchall()]
        return events

def mark_event_as_notified(event_id: int) -> None:
    """
    Marca un evento como notificado en la base de datos.

    Args:
        event_id (int): El ID del evento a actualizar.
    """
    with _get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE events SET notified = 1 WHERE id = ?", (event_id,))
        conn.commit()


# --- FUNCIONES DE GESTIÓN DE USUARIOS Y ALERTAS ---

def add_user_if_not_exists(chat_id: int) -> None:
    """
    Añade un nuevo usuario a la tabla 'users' si no existe.

    Args:
        chat_id (int): El ID del chat del usuario de Telegram.
    """
    with _get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO users (chat_id) VALUES (?)", (chat_id,))
        conn.commit()

def add_alert(chat_id: int, alert_type: str, alert_value: str) -> None:
    """
    Añade una nueva alerta para un usuario.

    Args:
        chat_id (int): El ID del chat del usuario.
        alert_type (str): El tipo de alerta ('artist' o 'club').
        alert_value (str): El valor a buscar (nombre del artista o club).
    """
    # Aseguramos que el usuario exista antes de añadir una alerta
    add_user_if_not_exists(chat_id)
    with _get_db_connection() as conn:
        cursor = conn.cursor()
        # Se guarda el valor en minúsculas para búsquedas insensibles a mayúsculas
        query = "INSERT OR IGNORE INTO alerts (chat_id, alert_type, alert_value) VALUES (?, ?, ?)"
        cursor.execute(query, (chat_id, alert_type, alert_value.lower()))
        conn.commit()

def get_user_alerts(chat_id: int) -> List[Dict[str, Any]]:
    """
    Obtiene todas las alertas de un usuario específico.

    Args:
        chat_id (int): El ID del chat del usuario.

    Returns:
        List[Dict[str, Any]]: Lista de las alertas del usuario.
    """
    with _get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, alert_type, alert_value FROM alerts WHERE chat_id = ?", (chat_id,))
        alerts = [dict(row) for row in cursor.fetchall()]
        return alerts

def delete_alert(alert_id: int) -> None:
    """
    Elimina una alerta específica por su ID.

    Args:
        alert_id (int): El ID de la alerta a eliminar.
    """
    with _get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        conn.commit()

def find_users_for_new_event(event: Dict[str, Any]) -> List[int]:
    """
    Encuentra todos los IDs de chat de usuarios que deben ser notificados sobre un nuevo evento.

    Args:
        event (Dict[str, Any]): El diccionario del evento nuevo.

    Returns:
        List[int]: Una lista de chat_ids únicos a notificar.
    """
    chat_ids_to_notify = set()
    with _get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. Buscar por club
        club_name_lower = (event.get('club_name') or "").lower()
        if club_name_lower:
            cursor.execute("""
                SELECT chat_id FROM alerts 
                WHERE alert_type = 'club' AND ? LIKE '%' || alert_value || '%'
            """, (club_name_lower,))
            for row in cursor.fetchall():
                chat_ids_to_notify.add(row['chat_id'])

        # 2. Buscar por artistas
        artists_list = [artist.strip().lower() for artist in (event.get('artists') or "").split(',')]
        for artist in artists_list:
            if artist:
                cursor.execute("""
                    SELECT chat_id FROM alerts 
                    WHERE alert_type = 'artist' AND ? LIKE '%' || alert_value || '%'
                """, (artist,))
                for row in cursor.fetchall():
                    chat_ids_to_notify.add(row['chat_id'])
                    
    return list(chat_ids_to_notify)


# --- SCRIPT DE EJECUCIÓN ---

if __name__ == '__main__':
    # Este bloque se ejecuta solo si se corre el archivo directamente (python database.py)
    # Es útil para la configuración inicial de la base de datos.
    setup_database()