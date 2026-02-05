# -*- coding: utf-8 -*-

"""
BCN Techno Radar Bot

Este bot de Telegram permite a los usuarios buscar eventos de música techno en Barcelona,
crear alertas personalizadas por artista o club, y recibir notificaciones
automáticas sobre nuevos eventos.

Funcionalidades principales:
- Consultar próximos eventos.
- Búsqueda avanzada por artista, club o fecha.
- Sistema de alertas para notificar al usuario sobre eventos de su interés.
- Paginación de resultados para una navegación cómoda.
- Notificador automático que busca nuevos eventos y avisa a los usuarios suscritos.
"""

# --- IMPORTACIONES ---
import asyncio
import logging
import re
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Importaciones de la librería python-telegram-bot
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Importaciones locales de la base de datos
from database import (
    setup_database,
    get_upcoming_events,
    search_events,
    search_events_by_date,
    add_user_if_not_exists,
    add_alert,
    get_user_alerts,
    delete_alert,
    find_users_for_new_event,
    get_unnotified_events,
    mark_event_as_notified,
)

# Importaciones del scraper para integrarlo en el bot
from scraper import fetch_events_from_api, transform_and_save_events


# --- CONFIGURACIÓN Y CONSTANTES ---

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Configuración del logging para monitorizar el bot
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("No se encontró el BOT_TOKEN en las variables de entorno.")
    sys.exit(1)

EVENTS_PER_PAGE = 5  # Número de eventos a mostrar por página

# --- ESTADOS DE CONVERSACIÓN ---
# Se definen los estados para las conversaciones de búsqueda y alertas.
(
    CHOOSING_SEARCH,
    TYPING_SEARCH,
    CHOOSING_DATE_RANGE,
    TYPING_CUSTOM_DATE,
    ALERT_MENU,
    ADDING_ARTIST,
    ADDING_CLUB,
) = range(7)


# --- FUNCIONES AUXILIARES ---

def escape_markdown_v2(text: str) -> str:
    """
    Escapa los caracteres especiales de MarkdownV2 para evitar errores de formato.

    Args:
        text (str): El texto a escapar.

    Returns:
        str: El texto con los caracteres especiales escapados.
    """
    if not isinstance(text, str):
        text = str(text)
    # Caracteres que deben ser escapados en MarkdownV2
    escape_chars = r'_*[]()~`>#+-.=|{}!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)


async def format_events_message(events: list, total_events: int, offset: int, search_info: dict = None) -> tuple:
    """
    Formatea una lista de eventos en un mensaje legible con paginación.

    Args:
        events (list): La lista de eventos a formatear.
        total_events (int): El número total de eventos encontrados.
        offset (int): El desplazamiento actual para la paginación.
        search_info (dict, optional): Información sobre la búsqueda actual (clave 'query_display').

    Returns:
        tuple: Una tupla con el mensaje formateado (str) y el teclado inline (InlineKeyboardMarkup).
    """
    if not events:
        if search_info:
            query_display = escape_markdown_v2(search_info['query_display'])
            return f"No encontré eventos para '{query_display}'\\.", None
        return "No hay más eventos próximos en la base de datos\\.", None

    # Título del mensaje
    if search_info:
        query_escaped = escape_markdown_v2(search_info['query_display'])
        message_title = (
            f"🔎 Resultados para '*{query_escaped}*' "
            f"\\({offset + 1}\\-{min(offset + EVENTS_PER_PAGE, total_events)} de {total_events}\\):\n\n"
        )
    else:
        message_title = "🗓️ *Próximas Fiestas en Barcelona*\n\n"

    # Cuerpo del mensaje
    message_body = ""
    for event in events:
        date_obj = datetime.strptime(event['event_date'], '%Y-%m-%d')
        formatted_date = date_obj.strftime("%a, %d de %b").replace('.', '')

        # Escapamos todos los campos para seguridad
        safe_name, safe_club, safe_date, safe_start, safe_end, safe_artists, safe_attending = map(
            escape_markdown_v2,
            [
                event['event_name'], event['club_name'], formatted_date,
                event['start_time'], event['end_time'], event['artists'],
                event['attending_count']
            ]
        )
        message_body += (
            f"🔥 *{safe_name}*\n"
            f"📍 Club: {safe_club}\n"
            f"📅 Fecha: {safe_date} `({safe_start} \\- {safe_end})`\n"
            f"🎵 Artistas: {safe_artists}\n"
            f"👥 Asistentes: {safe_attending}\n"
            f"🎟️ [Más Info]({event['source_link']})\n\n"
        )

    # Teclado de paginación con callbacks cortos (evita el límite de 64 bytes)
    keyboard = []
    row = []
    base_callback = "sp" if search_info else "p"

    if offset > 0:
        row.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"{base_callback}_{max(0, offset - EVENTS_PER_PAGE)}"))
    if (offset + EVENTS_PER_PAGE) < total_events:
        row.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"{base_callback}_{offset + EVENTS_PER_PAGE}"))

    if row:
        keyboard.append(row)

    return message_title + message_body, InlineKeyboardMarkup(keyboard)


# --- COMANDOS PRINCIPALES ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja el comando /start. Da la bienvenida al usuario y lo registra en la BD.
    """
    add_user_if_not_exists(update.message.chat_id)
    welcome_message = (
        "¡Bienvenido a BCN Techno Radar\\! 🚀\n\n"
        "Usa los siguientes comandos para empezar:\n"
        "/proximas \\- Ver las próximas fiestas\\.\n"
        "/buscar \\- Busca por artista, club o fecha\\.\n"
        "/alertas \\- Configura tus notificaciones\\."
    )
    await update.message.reply_text(
        welcome_message,
        parse_mode=ParseMode.MARKDOWN_V2
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja el comando /help. Muestra el mensaje de ayuda.
    """
    help_message = (
        "*Comandos Disponibles:*\n\n"
        "/start \\- Inicia el bot\\.\n"
        "/proximas \\- Muestra los próximos eventos programados\\.\n"
        "/buscar \\- Inicia una búsqueda interactiva de eventos\\.\n"
        "/alertas \\- Gestiona tus alertas de artistas o clubs favoritos\\.\n"
        "/cancel \\- Cancela cualquier operación actual \\(búsqueda, alerta, etc\\.\\)\\."
    )
    await update.message.reply_text(
        help_message,
        parse_mode=ParseMode.MARKDOWN_V2
    )


async def proximas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja el comando /proximas. Muestra la primera página de eventos futuros.
    """
    try:
        events, total_events = get_upcoming_events(limit=EVENTS_PER_PAGE, offset=0)
        message, reply_markup = await format_events_message(events, total_events, 0)
        await update.message.reply_text(
            message,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error en /proximas: {e}")
        await update.message.reply_text("Ha ocurrido un error al obtener los eventos. Inténtalo de nuevo.")


# --- CONVERSACIÓN DE BÚSQUEDA (/buscar) ---

async def buscar_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Punto de entrada de la conversación de búsqueda. Pregunta el tipo de búsqueda.
    """
    keyboard = [
        [
            InlineKeyboardButton("👤 Artista", callback_data="search_by_artist"),
            InlineKeyboardButton("🏠 Club", callback_data="search_by_club")
        ],
        [
            InlineKeyboardButton("🎉 Fiesta", callback_data="search_by_event_name"),
            InlineKeyboardButton("📅 Fecha", callback_data="search_by_date")
        ]
    ]
    await update.message.reply_text(
        "Perfecto. ¿Qué quieres buscar? Elige una opción:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_SEARCH


async def ask_for_search_term(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Pregunta al usuario el término de búsqueda (artista, club o nombre de fiesta).
    """
    query = update.callback_query
    await query.answer()

    search_type = query.data.split('_by_')[-1]
    context.user_data['search_type'] = search_type

    type_map = {
        'artist': 'del artista',
        'club': 'del club',
        'event_name': 'de la fiesta'
    }
    display_type = type_map.get(search_type, 'elemento')

    await query.edit_message_text(text=f"Ok, dime el nombre {display_type} que buscas:")
    return TYPING_SEARCH


async def received_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Procesa el término de búsqueda y muestra los resultados.
    """
    query_text = update.message.text
    search_type = context.user_data.get('search_type', 'artist')

    column_map = {
        'artist': 'artists',
        'club': 'club_name',
        'event_name': 'event_name'
    }
    search_by_db = column_map.get(search_type, 'artists')

    events, total = search_events(query=query_text, search_by=search_by_db, limit=EVENTS_PER_PAGE, offset=0)

    # Guardar contexto de búsqueda para la paginación
    context.user_data['search_context'] = {
        'type': search_type,
        'query': query_text,
        'query_display': query_text,
        'search_by_db': search_by_db,
    }
    search_info = {'query_display': query_text}

    message, markup = await format_events_message(events, total, 0, search_info)
    await update.message.reply_text(
        message,
        reply_markup=markup,
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True
    )

    # Limpiar solo datos de la conversación, no el contexto de búsqueda
    context.user_data.pop('search_type', None)
    return ConversationHandler.END


async def ask_for_date_range(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Muestra opciones de rangos de fecha para la búsqueda.
    """
    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton("Hoy", callback_data="date_range_today"),
            InlineKeyboardButton("Mañana", callback_data="date_range_tomorrow")
        ],
        [InlineKeyboardButton("Este fin de semana", callback_data="date_range_weekend")],
        [InlineKeyboardButton("✍️ Fecha Específica", callback_data="date_range_custom")]
    ]
    await query.edit_message_text(
        "Elige un rango de fechas:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_DATE_RANGE


async def received_date_range(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Procesa la opción de rango de fecha seleccionada y muestra los resultados.
    """
    query = update.callback_query
    await query.answer()

    choice = query.data.split('_')[-1]
    today = datetime.now()

    if choice == "today":
        start_date, end_date, query_display = today, today, "Hoy"
    elif choice == "tomorrow":
        start_date = end_date = today + timedelta(days=1)
        query_display = "Mañana"
    elif choice == "weekend":
        weekday = today.weekday()
        if weekday <= 4:  # Lunes a viernes: próximo fin de semana
            days_until_friday = (4 - weekday) % 7
            start_date = today + timedelta(days=days_until_friday)
        else:  # Sábado (5) o domingo (6): fin de semana actual
            days_since_friday = weekday - 4
            start_date = today - timedelta(days=days_since_friday)
        end_date = start_date + timedelta(days=2)
        query_display = "Este fin de semana"
    else:
        return ConversationHandler.END

    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')

    events, total = search_events_by_date(start_date_str, end_date_str, limit=EVENTS_PER_PAGE, offset=0)

    # Guardar contexto de búsqueda para la paginación
    context.user_data['search_context'] = {
        'type': 'date',
        'start_date': start_date_str,
        'end_date': end_date_str,
        'query_display': query_display,
    }
    search_info = {'query_display': query_display}

    message, markup = await format_events_message(events, total, 0, search_info)
    await query.edit_message_text(
        text=message,
        reply_markup=markup,
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True
    )
    return ConversationHandler.END


async def ask_for_custom_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Pide al usuario que introduzca una fecha en formato AAAA-MM-DD.
    """
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Ok, dime la fecha que buscas en formato `AAAA-MM-DD`\n"
        "Por ejemplo: `2025-09-27`",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    return TYPING_CUSTOM_DATE


async def received_custom_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Procesa la fecha personalizada introducida por el usuario.
    """
    date_text = update.message.text
    try:
        datetime.strptime(date_text, '%Y-%m-%d')
        start_date_str = end_date_str = date_text

        events, total = search_events_by_date(start_date_str, end_date_str, limit=EVENTS_PER_PAGE, offset=0)

        # Guardar contexto de búsqueda para la paginación
        context.user_data['search_context'] = {
            'type': 'date',
            'start_date': start_date_str,
            'end_date': end_date_str,
            'query_display': start_date_str,
        }
        search_info = {'query_display': start_date_str}

        message, markup = await format_events_message(events, total, 0, search_info)
        await update.message.reply_text(
            message,
            reply_markup=markup,
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True
        )
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text(
            "Formato de fecha incorrecto\\. Por favor, usa `AAAA-MM-DD`\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return TYPING_CUSTOM_DATE


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancela la conversación actual y limpia los datos de usuario.
    """
    await update.message.reply_text("Comando cancelado.")
    context.user_data.clear()
    return ConversationHandler.END


# --- CONVERSACIÓN DE ALERTAS (/alertas) ---

async def alertas_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Punto de entrada de la conversación de alertas. Muestra el menú principal.
    """
    keyboard = [
        [InlineKeyboardButton("➕ Añadir Alerta de Artista", callback_data="add_artist_alert")],
        [InlineKeyboardButton("➕ Añadir Alerta de Club", callback_data="add_club_alert")],
        [InlineKeyboardButton("🗑️ Ver/Borrar mis Alertas", callback_data="view_alerts")],
        [InlineKeyboardButton("✖️ Salir", callback_data="cancel_alert_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text("Gestiona tus alertas:", reply_markup=reply_markup)
    else:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Gestiona tus alertas:", reply_markup=reply_markup)

    return ALERT_MENU


async def ask_for_artist_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Pide el nombre del artista para crear una alerta.
    """
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Ok, dime el nombre del artista que quieres seguir:")
    return ADDING_ARTIST


async def ask_for_club_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Pide el nombre del club para crear una alerta.
    """
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Ok, dime el nombre del club que quieres seguir:")
    return ADDING_CLUB


async def received_artist_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Guarda la nueva alerta de artista en la base de datos.
    """
    artist_name = update.message.text
    add_alert(update.message.chat_id, 'artist', artist_name)
    await update.message.reply_text(f"¡Hecho! Te avisaré cuando haya un evento de '{artist_name}'.", parse_mode="HTML")
    return ConversationHandler.END


async def received_club_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Guarda la nueva alerta de club en la base de datos.
    """
    club_name = update.message.text
    add_alert(update.message.chat_id, 'club', club_name)
    await update.message.reply_text(f"¡Hecho! Te avisaré cuando haya un evento en '{club_name}'.", parse_mode="HTML")
    return ConversationHandler.END


async def view_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Muestra al usuario todas sus alertas activas con opción de borrarlas.
    """
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    alerts = get_user_alerts(chat_id)

    if not alerts:
        keyboard = [[InlineKeyboardButton("⬅️ Volver", callback_data="back_to_alert_menu")]]
        await query.edit_message_text(
            "No tienes ninguna alerta configurada.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ALERT_MENU

    message = "Tus alertas actuales:\n\n"
    keyboard = []
    for alert in alerts:
        icon = "👤" if alert['alert_type'] == 'artist' else "🏠"
        value_capitalized = alert['alert_value'].title()
        message += f"{icon} {value_capitalized}\n"
        keyboard.append([InlineKeyboardButton(f"🗑️ Borrar '{value_capitalized}'", callback_data=f"delete_alert_{alert['id']}")])

    keyboard.append([InlineKeyboardButton("⬅️ Volver al Menú", callback_data="back_to_alert_menu")])
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))
    return ALERT_MENU


async def delete_alert_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Maneja la pulsación del botón para borrar una alerta.
    """
    query = update.callback_query
    alert_id = int(query.data.split('_')[-1])
    chat_id = query.message.chat.id

    delete_alert(alert_id, chat_id)
    await query.answer(text="Alerta borrada.", show_alert=True)

    return await view_alerts(update, context)


async def end_alert_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cierra el menú de alertas y finaliza la conversación.
    """
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Menú de alertas cerrado.")
    return ConversationHandler.END


# --- MANEJADOR DE BOTONES (PAGINACIÓN) ---

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja los botones de paginación para los resultados de eventos.
    Los callbacks usan IDs cortos ('p_N' para próximas, 'sp_N' para búsqueda)
    y el contexto de búsqueda se almacena en context.user_data['search_context'].
    """
    query = update.callback_query
    await query.answer()

    data = query.data
    message, reply_markup = "", None

    try:
        if data.startswith("p_"):
            offset = int(data.split("_")[1])
            events, total_events = get_upcoming_events(limit=EVENTS_PER_PAGE, offset=offset)
            message, reply_markup = await format_events_message(events, total_events, offset)

        elif data.startswith("sp_"):
            offset = int(data.split("_")[1])
            sc = context.user_data.get('search_context')

            if not sc:
                await query.edit_message_text(
                    "La búsqueda ha expirado\\. Usa /buscar para iniciar una nueva\\.",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                return

            if sc['type'] == 'date':
                events, total = search_events_by_date(
                    sc['start_date'], sc['end_date'],
                    limit=EVENTS_PER_PAGE, offset=offset
                )
            else:
                events, total = search_events(
                    query=sc['query'], search_by=sc['search_by_db'],
                    limit=EVENTS_PER_PAGE, offset=offset
                )

            search_info = {'query_display': sc['query_display']}
            message, reply_markup = await format_events_message(events, total, offset, search_info)

        if message:
            await query.edit_message_text(
                text=message,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(f"Error en el handler de paginación: {e}")


# --- TAREAS PROGRAMADAS (JOB QUEUE) ---

async def check_and_notify(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Tarea periódica (cada 5 min) que busca nuevos eventos y notifica a los usuarios con alertas.
    """
    new_events = get_unnotified_events()

    if new_events:
        logger.info(f"Notificador: Se encontraron {len(new_events)} nuevos eventos para procesar.")

    for event in new_events:
        users_to_notify = find_users_for_new_event(event)

        if users_to_notify:
            date_obj = datetime.strptime(event['event_date'], '%Y-%m-%d')
            formatted_date = date_obj.strftime("%a, %d de %b").replace('.', '')

            message = (
                f"🔥 *¡ALERTA DE NUEVA FIESTA\\!*\n\n"
                f"*{escape_markdown_v2(event['event_name'])}*\n\n"
                f"📍 *Club:* {escape_markdown_v2(event['club_name'])}\n"
                f"📅 *Fecha:* {escape_markdown_v2(formatted_date)}\n"
                f"🎵 *Artistas:* {escape_markdown_v2(event['artists'])}\n\n"
                f"🎟️ [Ver Evento]({event['source_link']})"
            )

            for chat_id in users_to_notify:
                try:
                    if event['flyer_image']:
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=event['flyer_image'],
                            caption=message,
                            parse_mode=ParseMode.MARKDOWN_V2
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=message,
                            parse_mode=ParseMode.MARKDOWN_V2,
                            disable_web_page_preview=True
                        )
                except Exception as e:
                    logger.error(f"Error al notificar al usuario {chat_id} por evento {event['id']}: {e}")

        mark_event_as_notified(event['id'])

async def run_scraping_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Tarea periódica (cada 2 horas) para ejecutar el scraper y actualizar la base de datos.
    """
    logger.info("Iniciando tarea de scraping programada...")
    try:
        start_date = datetime.now()
        end_date = start_date + timedelta(days=365)
        api_events = await asyncio.to_thread(
            fetch_events_from_api, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')
        )
        if api_events:
            newly_added = await asyncio.to_thread(transform_and_save_events, api_events)
            logger.info(f"Scraping finalizado. {newly_added} eventos nuevos añadidos.")
        else:
            logger.info("Scraping finalizado. No se encontraron eventos en la API.")
    except Exception as e:
        logger.error(f"Error durante la ejecución del job de scraping: {e}")


# --- FUNCIÓN PRINCIPAL ---

def main() -> None:
    """
    Función principal que configura y ejecuta el bot.
    """
    # Inicializar la base de datos antes de arrancar
    setup_database()

    logger.info("Iniciando bot...")
    application = Application.builder().token(BOT_TOKEN).build()

    # --- (INTEGRACIÓN) ---
    # Configuración de las tareas periódicas (Job Queue)
    job_queue = application.job_queue
    # Tarea 1: Notificar a usuarios sobre nuevos eventos cada 5 minutos.
    job_queue.run_repeating(check_and_notify, interval=300, first=15)
    # Tarea 2: Actualizar la base de datos con nuevos eventos cada 2 horas.
    job_queue.run_repeating(run_scraping_job, interval=7200, first=10)

    # --- Handlers de Conversación ---
    search_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("buscar", buscar_start)],
        states={
            CHOOSING_SEARCH: [
                CallbackQueryHandler(ask_for_search_term, pattern="^search_by_(artist|club|event_name)$"),
                CallbackQueryHandler(ask_for_date_range, pattern="^search_by_date$")
            ],
            TYPING_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_search_query)],
            CHOOSING_DATE_RANGE: [
                CallbackQueryHandler(received_date_range, pattern="^date_range_(today|tomorrow|weekend)$"),
                CallbackQueryHandler(ask_for_custom_date, pattern="^date_range_custom$")
            ],
            TYPING_CUSTOM_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_custom_date)]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    alert_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("alertas", alertas_start)],
        states={
            ALERT_MENU: [
                CallbackQueryHandler(ask_for_artist_name, pattern="^add_artist_alert$"),
                CallbackQueryHandler(ask_for_club_name, pattern="^add_club_alert$"),
                CallbackQueryHandler(view_alerts, pattern="^view_alerts$"),
                CallbackQueryHandler(delete_alert_callback, pattern="^delete_alert_"),
                CallbackQueryHandler(alertas_start, pattern="^back_to_alert_menu$"),
                CallbackQueryHandler(end_alert_conversation, pattern="^cancel_alert_menu$"),
            ],
            ADDING_ARTIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_artist_alert)],
            ADDING_CLUB: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_club_alert)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    # --- Registro de Handlers ---
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("proximas", proximas))

    application.add_handler(search_conv_handler)
    application.add_handler(alert_conv_handler)

    application.add_handler(CallbackQueryHandler(button_handler, pattern="^(p_|sp_)"))

    logger.info("Bot iniciado y escuchando...")
    application.run_polling()


if __name__ == '__main__':
    main()
