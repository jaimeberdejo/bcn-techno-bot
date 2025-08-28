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
import logging
import re
from datetime import datetime, timedelta

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
    get_upcoming_events,
    search_events,
    search_events_by_date,
    add_user_if_not_exists,
    add_alert,
    get_user_alerts,
    delete_alert,
    find_users_for_new_event,
)

# --- CONFIGURACIÓN Y CONSTANTES ---

# Configuración del logging para monitorizar el bot
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constantes del Bot
BOT_TOKEN = "8204992864:AAGDjAaZ7TNDt8C50YAmgExH0qDrW_zaKw8"
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
        search_info (dict, optional): Información sobre la búsqueda actual.

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

    # Teclado de paginación
    keyboard = []
    row = []
    base_callback = f"search_{search_info['type']}_{search_info['query']}" if search_info else "page"

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
    # CORRECCIÓN: Se escapa el carácter '!' para evitar el error BadRequest.
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
    events, total_events = get_upcoming_events(limit=EVENTS_PER_PAGE, offset=0)
    message, reply_markup = await format_events_message(events, total_events, 0)
    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True
    )


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
        [InlineKeyboardButton("📅 Fecha", callback_data="search_by_date")]
    ]
    await update.message.reply_text(
        "Perfecto. ¿Qué quieres buscar? Elige una opción:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_SEARCH


async def ask_for_search_term(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Pregunta al usuario el término de búsqueda (nombre de artista o club).
    """
    query = update.callback_query
    await query.answer()
    
    search_type = query.data.split('_')[-1]
    context.user_data['search_type'] = search_type
    
    await query.edit_message_text(text=f"Ok, dime el nombre del {search_type} que buscas:")
    return TYPING_SEARCH


async def received_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Procesa el término de búsqueda y muestra los resultados.
    """
    query_text = update.message.text
    search_type = context.user_data.get('search_type', 'artist')
    search_by_db = 'artists' if search_type == 'artist' else 'club_name'
    
    events, total = search_events(query=query_text, search_by=search_by_db, limit=EVENTS_PER_PAGE, offset=0)
    search_info = {'type': search_type, 'query': query_text, 'query_display': query_text}
    
    message, markup = await format_events_message(events, total, 0, search_info)
    await update.message.reply_text(
        message,
        reply_markup=markup,
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True
    )
    
    context.user_data.clear()
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
        days_until_friday = (4 - today.weekday() + 7) % 7
        start_date = today + timedelta(days=days_until_friday)
        end_date = start_date + timedelta(days=2)
        query_display = "Este fin de semana"
    else:
        # Opción no válida, se termina la conversación.
        return ConversationHandler.END

    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    events, total = search_events_by_date(start_date_str, end_date_str, limit=EVENTS_PER_PAGE, offset=0)
    search_info = {'type': 'date', 'query': f"{start_date_str}_{end_date_str}", 'query_display': query_display}
    
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
        # Validamos el formato de la fecha
        datetime.strptime(date_text, '%Y-%m-%d')
        start_date_str = end_date_str = date_text
        
        events, total = search_events_by_date(start_date_str, end_date_str, limit=EVENTS_PER_PAGE, offset=0)
        search_info = {'type': 'date', 'query': f"{start_date_str}_{end_date_str}", 'query_display': start_date_str}
        
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
    
    # Si viene de un comando, responde. Si viene de un botón, edita.
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
    await update.message.reply_text(f"¡Hecho! Te avisaré cuando haya un evento de '{escape_markdown_v2(artist_name)}'\\.", parse_mode=ParseMode.MARKDOWN_V2)
    return ConversationHandler.END


async def received_club_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Guarda la nueva alerta de club en la base de datos.
    """
    club_name = update.message.text
    add_alert(update.message.chat_id, 'club', club_name)
    await update.message.reply_text(f"¡Hecho! Te avisaré cuando haya un evento en '{escape_markdown_v2(club_name)}'\\.", parse_mode=ParseMode.MARKDOWN_V2)
    return ConversationHandler.END


async def view_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Muestra al usuario todas sus alertas activas con opción de borrarlas.
    """
    query = update.callback_query
    await query.answer()
    
    alerts = get_user_alerts(query.from_user.id)
    
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
    
    delete_alert(alert_id)
    await query.answer(text="Alerta borrada.", show_alert=True)
    
    # Refrescamos la vista de alertas
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
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    message, reply_markup = "", None

    if data.startswith("page_"):
        offset = int(data.split("_")[1])
        events, total_events = get_upcoming_events(limit=EVENTS_PER_PAGE, offset=offset)
        message, reply_markup = await format_events_message(events, total_events, offset)
        
    elif data.startswith("search_"):
        parts = data.split('_')
        search_type = parts[1]
        
        if search_type == "date":
            start_date_str, end_date_str, offset = parts[2], parts[3], int(parts[4])
            events, total = search_events_by_date(start_date_str, end_date_str, limit=EVENTS_PER_PAGE, offset=offset)
            query_display = f"del {start_date_str} al {end_date_str}" if start_date_str != end_date_str else start_date_str
            search_info = {'type': 'date', 'query': f"{start_date_str}_{end_date_str}", 'query_display': query_display}
            message, reply_markup = await format_events_message(events, total, offset, search_info)
        else:
            # Reconstruimos la query por si contenía guiones bajos
            query_text = "_".join(parts[2:-1])
            offset = int(parts[-1])
            search_by_db = 'artists' if search_type == 'artist' else 'club_name'
            events, total = search_events(query=query_text, search_by=search_by_db, limit=EVENTS_PER_PAGE, offset=offset)
            search_info = {'type': search_type, 'query': query_text, 'query_display': query_text}
            message, reply_markup = await format_events_message(events, total, offset, search_info)

    if message:
        await query.edit_message_text(
            text=message,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True
        )


# --- NOTIFICADOR AUTOMÁTICO (JOB QUEUE) ---

async def check_and_notify(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Tarea periódica que busca nuevos eventos y notifica a los usuarios con alertas.
    """
    # Esta función debería idealmente usar las funciones del módulo 'database'
    # para mantener la lógica de la BD centralizada.
    # Por ahora, se mantiene la conexión directa para respetar el código original.
    from database import get_unnotified_events, mark_event_as_notified

    new_events = get_unnotified_events()
    
    if new_events:
        logger.info(f"Notificador: Se encontraron {len(new_events)} nuevos eventos para procesar.")

    for event in new_events:
        # La función find_users_for_new_event ya devuelve un dict del evento
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
        
        # Marcamos el evento como notificado
        mark_event_as_notified(event['id'])


# --- FUNCIÓN PRINCIPAL ---

def main() -> None:
    """
    Función principal que configura y ejecuta el bot.
    """
    logger.info("Iniciando bot...")
    application = Application.builder().token(BOT_TOKEN).build()

    # Configuración de la tarea periódica (Job Queue)
    job_queue = application.job_queue
    # Se ejecuta cada 5 minutos (300s), empezando 15s después de iniciar el bot.
    job_queue.run_repeating(check_and_notify, interval=300, first=15)

    # --- Handlers de Conversación ---
    search_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("buscar", buscar_start)],
        states={
            CHOOSING_SEARCH: [
                CallbackQueryHandler(ask_for_search_term, pattern="^search_by_(artist|club)$"),
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
    
    # Este handler debe ir después de las conversaciones para no interferir.
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^(page_|search_)"))

    logger.info("Bot iniciado y escuchando...")
    application.run_polling()


if __name__ == '__main__':
    main()