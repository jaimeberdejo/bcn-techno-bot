# scheduler.py
import schedule
import time
from scraper import scrape_ra_events, save_events_to_db

def job():
    print("Ejecutando tarea de scraping...")
    events = scrape_ra_events()
    if events:
        save_events_to_db(events)
        # Aquí iría la lógica de notificar sobre los nuevos eventos
    print("Tarea finalizada.")

# Ejecuta el job cada 2 horas
schedule.every(2).hours.do(job)

print("Scheduler iniciado. Esperando para ejecutar la tarea...")
while True:
    schedule.run_pending()
    time.sleep(1)