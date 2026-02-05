# scraper.py
import requests
import json
import time
import os
import logging
from datetime import datetime, timedelta

from database import get_db_connection

# --- Configuración ---
logger = logging.getLogger(__name__)

URL_API = 'https://ra.co/graphql'
HEADERS = {
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/117.0',
    'Referer': 'https://ra.co/events/es/barcelona'
}
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
QUERY_TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "graphql_query_template.json")
AREA_ID_BARCELONA = 20

def fetch_events_from_api(start_date_str, end_date_str):
    """Obtiene los eventos de la API de RA en un rango de fechas."""
    logger.info(f"Obteniendo todos los eventos desde {start_date_str} hasta {end_date_str}...")
    with open(QUERY_TEMPLATE_PATH, "r") as file:
        payload_template = json.load(file)

    payload_template["variables"]["filters"]["areas"]["eq"] = AREA_ID_BARCELONA
    payload_template["variables"]["filters"]["listingDate"]["gte"] = start_date_str
    payload_template["variables"]["filters"]["listingDate"]["lte"] = end_date_str

    all_events_in_range = []
    page_number = 1
    while True:
        logger.info(f"  Solicitando página {page_number}...")
        payload_template["variables"]["page"] = page_number
        try:
            response = requests.post(URL_API, headers=HEADERS, json=payload_template, timeout=30)
            response.raise_for_status()
            data = response.json()
            if 'errors' in data:
                logger.error(f"Error de la API: {data['errors']}")
                break

            events_page = data.get("data", {}).get("eventListings", {}).get("data", [])
            if not events_page:
                logger.info("No se encontraron más eventos. Terminando paginación.")
                break

            logger.info(f"  Se encontraron {len(events_page)} eventos en la página {page_number}.")
            all_events_in_range.extend(events_page)
            page_number += 1
            time.sleep(1) # Pausa para no saturar la API
        except requests.RequestException as e:
            logger.error(f"Error en la petición a la API: {e}")
            break
        except Exception as e:
            logger.error(f"Error inesperado: {e}")
            break

    return all_events_in_range

def transform_and_save_events(events):
    """
    Transforma los datos de la API al formato de nuestra BD y los guarda.
    Implementa una lógica de "upsert": inserta nuevos eventos y actualiza los existentes.
    """
    new_events_count = 0
    updated_events_count = 0
    processed_count = 0

    with get_db_connection() as conn:
        cursor = conn.cursor()

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

                images_list = event.get('images', [])
                flyer_image = ""
                if images_list:
                    flyer_filename = images_list[0].get('filename', '')
                    if flyer_filename:
                        flyer_image = "https://images.ra.co/" + flyer_filename

                source_link = "https://ra.co" + event.get('contentUrl', '')

                event_data = {
                    "event_name": event.get('title'),
                    "club_name": event.get('venue', {}).get('name', 'TBA'),
                    "event_date": date_obj.strftime('%Y-%m-%d'),
                    "start_time": start_time_obj.strftime('%H:%M'),
                    "end_time": end_time_obj.strftime('%H:%M'),
                    "artists": ", ".join(artists_list) or "Artistas por confirmar",
                    "attending_count": event.get('attending', 0),
                    "buy_link": source_link,
                    "flyer_image": flyer_image,
                    "source_link": source_link
                }

                cursor.execute("SELECT id FROM events WHERE source_link = ?", (source_link,))
                existing_event = cursor.fetchone()

                if existing_event:
                    update_query = """
                        UPDATE events SET
                            event_name = :event_name,
                            club_name = :club_name,
                            event_date = :event_date,
                            start_time = :start_time,
                            end_time = :end_time,
                            artists = :artists,
                            attending_count = :attending_count,
                            buy_link = :buy_link,
                            flyer_image = :flyer_image
                        WHERE source_link = :source_link
                    """
                    cursor.execute(update_query, event_data)
                    if cursor.rowcount > 0:
                        updated_events_count += 1
                else:
                    insert_query = """
                        INSERT INTO events
                        (event_name, club_name, event_date, start_time, end_time, artists, attending_count, buy_link, source_link, flyer_image)
                        VALUES (:event_name, :club_name, :event_date, :start_time, :end_time, :artists, :attending_count, :buy_link, :source_link, :flyer_image)
                    """
                    cursor.execute(insert_query, event_data)
                    if cursor.rowcount > 0:
                        new_events_count += 1

            except Exception as e:
                logger.warning(f"No se pudo procesar el evento '{event.get('title')}'. Razón: {e}")
                continue

        conn.commit()

    logger.info(f"Se procesaron {processed_count} eventos en total.")
    logger.info(f"Eventos nuevos añadidos: {new_events_count}")
    logger.info(f"Eventos existentes actualizados: {updated_events_count}")

    return new_events_count

if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger.info("--- Iniciando Scraper (API GraphQL - Todos los Eventos Futuros) ---")
    start_date = datetime.now()
    end_date = start_date + timedelta(days=365)
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    api_events = fetch_events_from_api(start_date_str, end_date_str)
    if api_events:
        logger.info(f"Se encontraron un total de {len(api_events)} eventos en el rango de fechas a través de la API.")
        transform_and_save_events(api_events)
    logger.info("--- Proceso de Scraping Finalizado ---")
