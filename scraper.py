# scraper.py
import requests
import json
import time
import sqlite3
from datetime import datetime, timedelta

# --- Configuración ---
URL_API = 'https://ra.co/graphql'
HEADERS = {
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/117.0',
    'Referer': 'https://ra.co/events/es/barcelona'
}
QUERY_TEMPLATE_PATH = "graphql_query_template.json"
AREA_ID_BARCELONA = 20

def fetch_events_from_api(start_date_str, end_date_str):
    print(f"-> Obteniendo todos los eventos desde {start_date_str} hasta {end_date_str}...")
    with open(QUERY_TEMPLATE_PATH, "r") as file:
        payload_template = json.load(file)
    payload_template["variables"]["filters"]["areas"]["eq"] = AREA_ID_BARCELONA
    payload_template["variables"]["filters"]["listingDate"]["gte"] = start_date_str
    payload_template["variables"]["filters"]["listingDate"]["lte"] = end_date_str
    all_events_in_range = []
    page_number = 1
    while True:
        print(f"  - Solicitando página {page_number}...")
        payload_template["variables"]["page"] = page_number
        try:
            response = requests.post(URL_API, headers=HEADERS, json=payload_template, timeout=30)
            response.raise_for_status()
            data = response.json()
            if 'errors' in data:
                print(f"  -> Error de la API: {data['errors']}")
                break
            events_page = data.get("data", {}).get("eventListings", {}).get("data", [])
            if not events_page:
                print("  -> No se encontraron más eventos. Terminando paginación.")
                break
            print(f"  -> Se encontraron {len(events_page)} eventos en la página {page_number}.")
            all_events_in_range.extend(events_page)
            page_number += 1
            time.sleep(1)
        except Exception as e:
            print(f"  -> Error en la petición: {e}")
            break
    return all_events_in_range

def transform_and_save_events(events):
    """
    Transforma los datos de la API al formato de nuestra BD y los guarda.
    Versión mejorada para manejar eventos sin imagen de flyer.
    """
    conn = sqlite3.connect('techno_events.db')
    cursor = conn.cursor()
    new_events_count = 0
    processed_count = 0

    for item in events:
        event = item.get('event', {})
        if not event:
            continue

        processed_count += 1
        try:
            date_obj = datetime.fromisoformat(event['date'].replace('Z', '+00:00'))
            start_time_obj = datetime.fromisoformat(event['startTime'].replace('Z', '+00:00'))
            end_time_obj = datetime.fromisoformat(event['endTime'].replace('Z', '+00:00'))

            artists_list = [artist['name'] for artist in event.get('artists', []) if artist.get('name')]
            
            # --- CÓDIGO CORREGIDO PARA LAS IMÁGENES ---
            images_list = event.get('images', []) # Obtenemos la lista de imágenes
            flyer_image = "" # Por defecto, no hay imagen
            if images_list: # Solo si la lista NO está vacía...
                flyer_filename = images_list[0].get('filename', '')
                if flyer_filename:
                    flyer_image = "https://images.ra.co/" + flyer_filename
            # -----------------------------------------

            event_data = {
                "event_name": event.get('title'),
                "club_name": event.get('venue', {}).get('name', 'TBA'),
                "event_date": date_obj.strftime('%Y-%m-%d'),
                "start_time": start_time_obj.strftime('%H:%M'),
                "end_time": end_time_obj.strftime('%H:%M'),
                "artists": ", ".join(artists_list) or "Artistas por confirmar",
                "attending_count": event.get('attending', 0),
                "buy_link": "https://ra.co" + event.get('contentUrl', ''),
                "source_link": "https://ra.co" + event.get('contentUrl', ''),
                "flyer_image": flyer_image,
            }

            cursor.execute('''
                INSERT OR IGNORE INTO events 
                (event_name, club_name, event_date, start_time, end_time, artists, attending_count, buy_link, source_link, flyer_image)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', tuple(event_data.values()))
            
            if cursor.rowcount > 0:
                new_events_count += 1
        except Exception as e:
            # Mantenemos esto por si surge un error diferente
            print(f"  -> Advertencia: No se pudo procesar el evento '{event.get('title')}'. Razón: {e}")
            continue

    conn.commit()
    conn.close()
    
    print(f"\n-> Se procesaron {processed_count} eventos en total.")
    return new_events_count


    
# El bloque __main__ no necesita cambios
if __name__ == '__main__':
    print("--- Iniciando Scraper (API GraphQL - Todos los Eventos Futuros) ---")
    start_date = datetime.now()
    end_date = start_date + timedelta(days=365)
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    api_events = fetch_events_from_api(start_date_str, end_date_str)
    if api_events:
        print(f"\nSe encontraron un total de {len(api_events)} eventos en el rango de fechas a través de la API.")
        newly_added = transform_and_save_events(api_events)
        print(f"\nTotal de eventos nuevos añadidos a la base de datos: {newly_added}")
    print("\n--- Proceso de Scraping Finalizado ---")