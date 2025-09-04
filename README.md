
# BCN Techno Radar Bot 🚀

BCN Techno Radar es un bot de Telegram diseñado para los amantes de la música techno en Barcelona. El bot centraliza la información de eventos, permite búsquedas avanzadas y, lo más importante, envía notificaciones personalizadas para que nunca te pierdas a tus artistas, fiestas o clubs favoritos.

## ✨ Características

* **Eventos Próximos**: Consulta una lista paginada de los próximos eventos de la ciudad con `/proximas`.
* **Búsqueda Avanzada**: Utiliza el comando `/buscar` para encontrar eventos por:
    * 👤 Artista
    * 🏠 Club
    * 🎉 Nombre de la fiesta
    * 📅 Fecha (hoy, mañana, fin de semana o una fecha específica).
* **Alertas Personalizadas**: Configura notificaciones automáticas con `/alertas`. El bot te enviará un mensaje privado tan pronto como se anuncie un nuevo evento que coincida con tus alertas.
* **Notificaciones Automáticas**: El bot revisa periódicamente si hay nuevos eventos y notifica a los usuarios suscritos a las alertas relevantes.
* **Fuente de Datos Fiable**: Toda la información se obtiene y actualiza directamente desde la API de Resident Advisor (RA).

## 🛠️ Instalación y Puesta en Marcha

Sigue estos pasos para poner en funcionamiento el bot en tu propio servidor o máquina local.

### Prerrequisitos

* Python 3.10 o superior.
* Un token de Bot de Telegram obtenido de [@BotFather](https://t.me/BotFather).

### Pasos de Instalación

1.  **Clona el repositorio**:
    ```bash
    git clone [https://github.com/tu-usuario/bcn-techno-bot.git](https://github.com/tu-usuario/bcn-techno-bot.git)
    cd bcn-techno-bot
    ```

2.  **Crea y activa un entorno virtual**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Instala las dependencias**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configura las variables de entorno**:
    Crea un archivo llamado `.env` en la raíz del proyecto.
    ```bash
    nano .env
    ```
    Añade tu token del bot dentro del archivo:
    ```
    BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123"
    ```

5.  **Inicializa la base de datos**:
    La primera vez que configures el proyecto, ejecuta el siguiente comando para crear el archivo `techno_events.db` y las tablas necesarias.
    ```bash
    python3 database.py
    ```

6.  **Ejecuta el bot**:
    Para probar que todo funciona correctamente, inicia el bot manualmente.
    ```bash
    python3 bot.py
    ```
    Si todo está bien, deberías ver el mensaje "Bot iniciado y escuchando..." en tu terminal.

## 🚀 Despliegue en Producción

Para que el bot se ejecute 24/7 en un servidor, se recomienda configurarlo como un servicio de `systemd`. Esto asegurará que el bot se reinicie automáticamente si falla o si el servidor se reinicia.

1.  **Crea el archivo de servicio**:
    ```bash
    sudo nano /etc/systemd/system/techno-bot.service
    ```

2.  **Pega la siguiente configuración** (recuerda cambiar las rutas para que coincidan con tu configuración):
    ```ini
    [Unit]
    Description=BCN Techno Radar Telegram Bot
    After=network.target

    [Service]
    User=ubuntu
    Group=ubuntu
    WorkingDirectory=/home/ubuntu/bcn-techno-bot
    ExecStart=/home/ubuntu/bcn-techno-bot/venv/bin/python3 /home/ubuntu/bcn-techno-bot/bot.py
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target
    ```

3.  **Inicia y habilita el servicio**:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl start techno-bot
    sudo systemctl enable techno-bot
    ```

4.  **Para ver los logs del bot**:
    ```bash
    sudo journalctl -u techno-bot -f
    ```

## 🤖 Uso del Bot

Interactúa con el bot en Telegram usando los siguientes comandos:

* `/start` - Inicia la conversación con el bot.
* `/proximas` - Muestra los próximos eventos programados.
* `/buscar` - Inicia una búsqueda interactiva.
* `/alertas` - Permite añadir o eliminar alertas personalizadas.
* `/help` - Muestra el mensaje de ayuda.
* `/cancel` - Cancela cualquier operación en curso (búsqueda o creación de alerta).
