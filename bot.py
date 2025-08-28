# bot.py
import logging
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Importamos las funciones, incluida la nueva de búsqueda por fecha
from database import (
    get_upcoming_events, 
    search_events, 
    search_events_by_date, # <-- NUEVA
    add_user_if_not_exists
)

# --- CONFIGURACIÓN ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
BOT_TOKEN = "8204992864:AAGDjAaZ7TNDt8C50YAmgExH0qDrW_zaKw8" 
EVENTS_PER_PAGE = 5

# --- ESTADOS PARA LA CONVERSACIÓN ---
CHOOSING_SEARCH, TYPING_SEARCH, CHOOSING_DATE_RANGE = range(3)

# --- FUNCIONES AUXILIARES ---
def escape_markdown_v2(text: str) -> str:
    # (sin cambios en esta función)
    if not isinstance(text, str): text = str(text)
    escape_chars = r'_*[]()~`>#+-.=|{}!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

async def format_events_message(events, total_events, offset, search_info=None):
    # (sin cambios en esta función)
    if not events:
        if search_info: return f"No encontré eventos para '{escape_markdown_v2(search_info['query_display'])}'\\.", None
        return "No hay más eventos próximos en la base de datos\\.", None
    if search_info:
        query_escaped = escape_markdown_v2(search_info['query_display'])
        message_title = f"🔎 Resultados para '*{query_escaped}*' \\({offset+1}\\-{min(offset+EVENTS_PER_PAGE, total_events)} de {total_events}\\):\n\n"
    else: message_title = "🗓️ *Próximas Fiestas en Barcelona*\n\n"
    message_body = ""
    for event in events:
        date_obj = datetime.strptime(event['event_date'], '%Y-%m-%d')
        formatted_date = date_obj.strftime("%a, %d de %b").replace('.', '')
        safe_name = escape_markdown_v2(event['event_name'])
        safe_club = escape_markdown_v2(event['club_name'])
        safe_date = escape_markdown_v2(formatted_date)
        safe_start_time = escape_markdown_v2(event['start_time'])
        safe_end_time = escape_markdown_v2(event['end_time'])
        safe_artists = escape_markdown_v2(event['artists'])
        safe_attending = escape_markdown_v2(event['attending_count'])
        message_body += (f"🔥 *{safe_name}*\n📍 Club: {safe_club}\n📅 Fecha: {safe_date} `({safe_start_time} \\- {safe_end_time})`\n🎵 Artistas: {safe_artists}\n👥 Asistentes: {safe_attending}\n🎟️ [Más Info]({event['source_link']})\n\n")
    keyboard = []
    row = []
    base_callback = f"search_{search_info['type']}_{search_info['query']}" if search_info else "page"
    if offset > 0: row.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"{base_callback}_{max(0, offset - EVENTS_PER_PAGE)}"))
    if (offset + EVENTS_PER_PAGE) < total_events: row.append(InlineKeyboardButton("Siguiente ➡️", callback_data=f"{base_callback}_{offset + EVENTS_PER_PAGE}"))
    if row: keyboard.append(row)
    return message_title + message_body, InlineKeyboardMarkup(keyboard)

# --- COMANDOS Y HANDLERS BÁSICOS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "¡Bienvenido a BCN Techno Radar\\! 🚀\n\n"
        "Usa los siguientes comandos para empezar:\n"
        "/proximas \\- Ver las próximas fiestas\\.\n"
        "/buscar \\- Busca por artista o club \\.\n"
        "/alertas \\- Configura tus notificaciones \\(próximamente\\)\\.\n"
        "/help \\- Muestra esta ayuda de nuevo\\."
    )
    await update.message.reply_text(welcome_message, parse_mode=ParseMode.MARKDOWN_V2)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la lista de comandos."""
    await start(update, context)

async def proximas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    events, total_events = get_upcoming_events(limit=EVENTS_PER_PAGE, offset=0)
    message, reply_markup = await format_events_message(events, total_events, 0)
    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)

# --- CONVERSACIÓN DE BÚSQUEDA (ACTUALIZADA) ---
async def buscar_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [
            InlineKeyboardButton("👤 Artista", callback_data="search_by_artist"),
            InlineKeyboardButton("🏠 Club", callback_data="search_by_club"),
        ],
        [InlineKeyboardButton("📅 Fecha", callback_data="search_by_date")] # <-- NUEVO BOTÓN
    ]
    await update.message.reply_text("Perfecto. ¿Qué quieres buscar? Elige una opción:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING_SEARCH

async def ask_for_search_term(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['search_type'] = query.data.split('_')[-1]
    await query.edit_message_text(text=f"Ok, dime el nombre del {context.user_data['search_type']} que buscas:")
    return TYPING_SEARCH

async def received_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query_text = update.message.text
    search_type = context.user_data.get('search_type', 'artist')
    search_by_db = 'artists' if search_type == 'artist' else 'club_name'
    events, total = search_events(query=query_text, search_by=search_by_db, limit=EVENTS_PER_PAGE, offset=0)
    search_info = {'type': search_type, 'query': query_text, 'query_display': query_text}
    message, markup = await format_events_message(events, total, 0, search_info)
    await update.message.reply_text(message, reply_markup=markup, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
    context.user_data.clear()
    return ConversationHandler.END

async def ask_for_date_range(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """NUEVA FUNCIÓN: Muestra los botones de rangos de fecha."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [
            InlineKeyboardButton("Hoy", callback_data="date_range_today"),
            InlineKeyboardButton("Mañana", callback_data="date_range_tomorrow"),
        ],
        [InlineKeyboardButton("Este fin de semana", callback_data="date_range_weekend")]
    ]
    await query.edit_message_text("Elige un rango de fechas:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING_DATE_RANGE

async def received_date_range(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """NUEVA FUNCIÓN: Procesa la elección del rango de fecha y busca en la BD."""
    query = update.callback_query
    await query.answer()
    
    choice = query.data.split('_')[-1]
    today = datetime.now()
    
    if choice == "today":
        start_date = today
        end_date = today
        query_display = "Hoy"
    elif choice == "tomorrow":
        start_date = today + timedelta(days=1)
        end_date = start_date
        query_display = "Mañana"
    elif choice == "weekend":
        # Viernes es el día 4 (lunes=0). Sumamos los días que faltan para el viernes.
        days_until_friday = (4 - today.weekday() + 7) % 7
        start_date = today + timedelta(days=days_until_friday)
        end_date = start_date + timedelta(days=2) # Viernes, Sábado, Domingo
        query_display = "Este fin de semana"
    else:
        return ConversationHandler.END

    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')

    events, total = search_events_by_date(start_date_str, end_date_str, limit=EVENTS_PER_PAGE, offset=0)
    
    # Preparamos la info para el formateador de mensajes y la paginación
    search_info = {'type': 'date', 'query': f"{start_date_str}_{end_date_str}", 'query_display': query_display}
    message, markup = await format_events_message(events, total, 0, search_info)
    
    await query.edit_message_text(text=message, reply_markup=markup, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Búsqueda cancelada.")
    context.user_data.clear()
    return ConversationHandler.END

# --- MANEJADOR DE BOTONES (PAGINACIÓN ACTUALIZADO) ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            # Paginación de búsqueda por fecha: search_date_YYYY-MM-DD_YYYY-MM-DD_offset
            start_date_str, end_date_str, offset = parts[2], parts[3], int(parts[4])
            events, total = search_events_by_date(start_date_str, end_date_str, limit=EVENTS_PER_PAGE, offset=offset)
            query_display = f"del {start_date_str} al {end_date_str}"
            search_info = {'type': 'date', 'query': f"{start_date_str}_{end_date_str}", 'query_display': query_display}
            message, reply_markup = await format_events_message(events, total, offset, search_info)
        else: # artist o club
            query_text, offset = "_".join(parts[2:-1]), int(parts[-1])
            search_by_db = 'artists' if search_type == 'artist' else 'club_name'
            events, total = search_events(query=query_text, search_by=search_by_db, limit=EVENTS_PER_PAGE, offset=offset)
            search_info = {'type': search_type, 'query': query_text, 'query_display': query_text}
            message, reply_markup = await format_events_message(events, total, offset, search_info)

    if message:
        await query.edit_message_text(text=message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)

# --- FUNCIÓN PRINCIPAL ---
def main():
    print("Iniciando bot...")
    application = Application.builder().token(BOT_TOKEN).build()

    search_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("buscar", buscar_start)],
        states={
            CHOOSING_SEARCH: [
                CallbackQueryHandler(ask_for_search_term, pattern="^search_by_(artist|club)$"),
                CallbackQueryHandler(ask_for_date_range, pattern="^search_by_date$"), # <-- NUEVA RUTA
            ],
            TYPING_SEARCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_search_query),
            ],
            CHOOSING_DATE_RANGE: [
                CallbackQueryHandler(received_date_range, pattern="^date_range_") # <-- NUEVO ESTADO
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("proximas", proximas))
    application.add_handler(search_conv_handler)
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^(page_|search_)"))

    print("Bot iniciado y escuchando...")
    application.run_polling()

if __name__ == '__main__':
    main()