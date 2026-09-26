"""Minimal localization: strings are written in English and translated at runtime.

The language follows the operating system (Spanish if the system is in Spanish,
English otherwise) and can be overridden with set_language().
"""

import locale
import os

SUPPORTED = ("en", "es")
_lang = None


def system_language():
    """Best-effort detection of the OS language, without requiring Qt."""
    try:
        from PySide6.QtCore import QLocale
        name = QLocale.system().name()  # e.g. "es_ES", "en_US"
    except Exception:  # noqa: BLE001 - Qt is optional (CLI)
        name = (os.environ.get("LC_ALL") or os.environ.get("LANG") or
                (locale.getlocale()[0] or ""))
    return "es" if name.lower().startswith(("es", "spanish")) else "en"


def set_language(lang=None):
    """lang: 'en', 'es' or None/'system' to follow the operating system."""
    global _lang
    _lang = lang if lang in SUPPORTED else system_language()
    return _lang


def language():
    return _lang or set_language()


def tr(text, *args):
    s = ES.get(text, text) if language() == "es" else text
    return s % args if args else s


ES = {
    # --- keyboard / protocol
    "Static": "Estático",
    "Single on": "Tecla se enciende",
    "Single off": "Tecla se apaga",
    "Glittering": "Destellos",
    "Falling": "Lluvia",
    "Colourful": "Multicolor",
    "Breath": "Respiración",
    "Spectrum": "Espectro",
    "Outward": "Hacia afuera",
    "Scrolling": "Desplazamiento",
    "Rolling": "Rodando",
    "Rotating": "Rotación",
    "Explode": "Explosión",
    "Launch": "Lanzamiento",
    "Ripples": "Ondas",
    "Flowing": "Flujo",
    "Pulsating": "Pulso",
    "Tilt": "Inclinación",
    "Shuttle": "Lanzadera",
    "Off": "Apagado",
    "Never": "Nunca",
    "1 minute": "1 minuto",
    "5 minutes": "5 minutos",
    "30 minutes": "30 minutos",
    "Keyboard connected.": "Teclado conectado.",
    "The keyboard is connected via Bluetooth or 2.4G. Connect it with the USB cable (wired mode); "
    "it can't be configured wirelessly.":
        "El teclado está conectado por Bluetooth o 2.4G. Conéctalo con el cable USB (modo cable); "
        "de forma inalámbrica no se puede configurar.",
    "Keyboard not found. Connect it with the USB cable and close the official AJAZZ driver if it's open.":
        "No encuentro el teclado. Conéctalo con el cable USB y cierra el driver oficial de AJAZZ si está abierto.",
    "Couldn't open the keyboard (%s). On Mac: System Settings > Privacy & Security > Input Monitoring, "
    "and allow this app.":
        "No se pudo abrir el teclado (%s). En Mac: Ajustes del Sistema > Privacidad y seguridad > "
        "Monitorización de entrada, y permite esta app.",
    "The keyboard rejected command 0x%02X.": "El teclado rechazó el comando 0x%02X.",
    "  the keyboard asked to retry…": "  el teclado pidió reintento…",
    "The keyboard didn't answer command 0x%02X.": "El teclado no respondió al comando 0x%02X.",
    "The keyboard's screen interface wasn't found.": "No se encontró la interfaz de la pantalla del teclado.",
    "Time set: %s": "Hora puesta: %s",
    "Lights: %s": "Luces: %s",
    "Settings saved.": "Ajustes guardados.",
    "Sending the image failed (chunk %d).": "Falló el envío de la imagen (bloque %d).",
    "Screen updated (%d frames).": "Pantalla actualizada (%d cuadros).",

    # --- app: general
    "Clock": "Reloj",
    "Lights": "Luces",
    "Screen": "Pantalla",
    "Settings": "Ajustes",
    "Shortcuts": "Atajos",
    "Done.": "Listo.",
    "Unexpected error: %s": "Error inesperado: %s",
    "The official AJAZZ driver (DeviceDriver.exe) is open and sends its own commands to the keyboard, "
    "which mixes up the changes. Close it (also from the system tray) and try again.":
        "El driver oficial de AJAZZ (DeviceDriver.exe) está abierto y le manda sus propios comandos al "
        "teclado, lo que mezcla los cambios. Ciérralo (también desde la bandeja) y vuelve a intentarlo.",
    "Close the official AJAZZ driver.": "Cierra el driver oficial de AJAZZ.",
    "The keyboard stopped responding. Unplug and reconnect the cable and try again.":
        "El teclado dejó de responder. Desconecta y vuelve a conectar el cable e inténtalo otra vez.",
    "Connected by cable": "Conectado por cable",
    "Bluetooth": "Bluetooth",
    " · battery %d %%": " · batería %d %%",
    "Keyboard not connected": "Teclado no conectado",
    "To configure the keyboard, connect it with the USB cable.":
        "Para configurar el teclado conéctalo con el cable USB.",
    "Time synced on connect.": "Hora sincronizada al conectar.",
    "Sync time": "Sincronizar hora",
    "Open %s": "Abrir %s",
    "Quit": "Salir",
    "Still running in the background to sync the time when the keyboard is connected.":
        "Sigo en segundo plano para sincronizar la hora al conectar el teclado.",
    "Couldn't change the startup setting: %s": "No se pudo cambiar el inicio automático: %s",

    # --- app: clock
    "Set the time on the keyboard's screen.": "Pon en hora la pantalla del teclado.",
    "Sync with this computer": "Sincronizar con este equipo",
    "Requires the USB cable. Over Bluetooth or 2.4G the keyboard doesn't accept the time.":
        "Necesita el cable USB. Por Bluetooth o 2.4G el teclado no acepta la hora.",
    "Send": "Enviar",
    "Date and time": "Fecha y hora",
    "Custom time": "Hora personalizada",
    "Sync when the cable is connected": "Sincronizar al conectar el cable",
    "Sets the time automatically every time you plug in the keyboard, for example to charge it.":
        "Pone la hora sola cada vez que enchufas el teclado, por ejemplo al cargarlo.",
    "Open at login": "Abrir al iniciar sesión",
    "Stays in the background, in the menu bar.": "Se queda en segundo plano, en la barra de menús.",
    "Automatic": "Automático",
    "dddd, MMMM d, yyyy": "dddd, d 'de' MMMM 'de' yyyy",

    # --- app: lights
    "Pick an effect and press Apply.": "Elige un efecto y pulsa Aplicar.",
    "Effect": "Efecto",
    "One color": "Un color",
    "Multicolor": "Multicolor",
    "Other…": "Otro…",
    "Color": "Color",
    "Left": "Izquierda",
    "Right": "Derecha",
    "Up": "Arriba",
    "Down": "Abajo",
    "Direction": "Dirección",
    "Color mode": "Modo de color",
    "Brightness": "Brillo",
    "Speed": "Velocidad",
    "Effect settings": "Ajustes del efecto",
    "Lights won't turn on? They may be off from the keyboard itself: press Fn + X.":
        "¿No se encienden? Puede que estén apagadas desde el teclado: pulsa Fn + X.",
    "Apply lights": "Aplicar luces",
    "Light color": "Color de las luces",
    "Lights applied: %s.": "Luces aplicadas: %s.",

    # --- app: screen
    "Upload an image or an animated GIF to the keyboard's screen.":
        "Sube una imagen o un GIF animado a la pantalla del teclado.",
    "No image": "Sin imagen",
    "160 × 96 pixels · up to 255 frames": "160 × 96 píxeles · hasta 255 cuadros",
    "Choose image or GIF…": "Elegir imagen o GIF…",
    "Fill": "Llenar",
    "Fit": "Encajar",
    "Stretch": "Estirar",
    "Scaling": "Ajuste",
    "Fill crops the edges; Fit adds black bars.": "Llenar recorta los bordes; Encajar deja franjas negras.",
    "Fixed speed": "Velocidad fija",
    "Ignores the GIF's own timing and uses this time per frame.":
        "Ignora la velocidad del GIF y usa este tiempo por cuadro.",
    "Options": "Opciones",
    "Uploading an image replaces the current animation. To see only the clock and status, "
    "hide the animation with Fn + Del on the keyboard.":
        "Subir una imagen reemplaza la animación actual. Para ver solo el reloj y el estado, "
        "oculta la animación con Fn + Supr en el teclado.",
    "Upload to screen": "Subir a la pantalla",
    "Choose image": "Elegir imagen",
    "Images (*.gif *.png *.jpg *.jpeg *.webp *.bmp)": "Imágenes (*.gif *.png *.jpg *.jpeg *.webp *.bmp)",
    "Couldn't open the image: %s": "No se pudo abrir la imagen: %s",
    "%s · %d frame": "%s · %d cuadro",
    "%s · %d frames": "%s · %d cuadros",
    "Image uploaded to the screen.": "Imagen subida a la pantalla.",

    # --- app: settings
    "System": "Sistema",
    "Light": "Claro",
    "Dark": "Oscuro",
    "Appearance": "Apariencia",
    "System follows your computer's light or dark mode.": "Sistema sigue el modo claro u oscuro de tu equipo.",
    "Language": "Idioma",
    "System uses your computer's language.": "Sistema usa el idioma de tu equipo.",
    "App": "Aplicación",
    "Block %s key": "Bloquear tecla %s",
    "Cmd / Windows": "Cmd / Windows",
    "Windows": "Windows",
    "Block Alt + F4": "Bloquear Alt + F4",
    "Block Alt + Tab": "Bloquear Alt + Tab",
    "Turn lights off when idle": "Apagar luces tras inactividad",
    "Key response time": "Tiempo de respuesta de teclas",
    "1 = fastest · 5 = most stable (avoids double presses).":
        "1 = más rápido · 5 = más estable (evita dobles pulsaciones).",
    "Keyboard": "Teclado",
    "Game mode": "Modo juego",
    "Prevents leaving your game by accident.": "Evita salir del juego por accidente.",
    "These settings are stored on the keyboard itself.": "Estos ajustes se guardan en el propio teclado.",
    "Save to keyboard": "Guardar en el teclado",
    "%s %s · protocol extracted from the official AJAZZ driver":
        "%s %s · protocolo extraído del driver oficial de AJAZZ",
    "Settings saved to the keyboard.": "Ajustes guardados en el teclado.",

    # --- app: shortcuts
    "They work directly on the keyboard, without the app (per the AK832 Pro manual).":
        "Funcionan directamente en el teclado, sin la app (según el manual del AK832 Pro).",
    "Show or hide the animation (without it you see the clock and status)":
        "Mostrar u ocultar la animación (sin ella se ven el reloj y el estado)",
    "Turn the screen on or off": "Encender o apagar la pantalla",
    "Move left in the screen menu": "Moverse a la izquierda en el menú de la pantalla",
    "Move right in the screen menu": "Moverse a la derecha en el menú de la pantalla",
    "Confirm the selected option": "Confirmar la opción elegida",
    "Turn the lights on or off": "Encender o apagar las luces",
    "Cycle through the 20 effects": "Cambiar entre los 20 efectos",
    "Brightness up (5 levels)": "Subir brillo (5 niveles)",
    "Brightness down": "Bajar brillo",
    "Change the color": "Cambiar el color",
    "Change the effect direction": "Cambiar la dirección del efecto",
    "Faster": "Más velocidad",
    "Slower": "Menos velocidad",
    "Gaming light modes": "Modos de luz para juegos",
    "FPS mode": "Modo FPS",
    "LOL mode": "Modo LOL",
    "Office mode": "Modo oficina",
    "Record your own light mode": "Grabar tu propio modo de luces",
    "Connection": "Conexión",
    "Bluetooth 1 (hold 3 s to pair)": "Bluetooth 1 (mantén 3 s para emparejar)",
    "Bluetooth 2 (hold 3 s to pair)": "Bluetooth 2 (mantén 3 s para emparejar)",
    "Bluetooth 3 (hold 3 s to pair)": "Bluetooth 3 (mantén 3 s para emparejar)",
    "2.4G receiver (hold 3 s to pair)": "Receptor 2.4G (mantén 3 s para emparejar)",
    "Hold 3-5 s to factory reset": "Mantén 3-5 s para restaurar de fábrica",
    "Del": "Supr",
    "PgUp": "Re Pág",
    "PgDn": "Av Pág",
    "Space": "Espacio",
}
