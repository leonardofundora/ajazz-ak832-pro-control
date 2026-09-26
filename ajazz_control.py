"""AJAZZ Control: reloj, luces, pantalla y ajustes del AK832 Pro en Mac y Windows."""

import os
import plistlib
import sys
import threading
import traceback
from datetime import datetime

from PySide6.QtCore import QDate, QDateTime, QLocale, QObject, QRunnable, QSettings, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QImage, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QGraphicsOpacityEffect, QColorDialog, QComboBox, QDateTimeEdit, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QSlider, QSpinBox, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

import ui_theme as T
from ak832 import __version__
from ak832 import protocol as P
from ak832 import screen
from ak832.battery import read_battery
from ak832.device import Keyboard, KeyboardError, connection_state

APP_NAME = "AJAZZ Control"
IS_MAC = sys.platform == "darwin"
# Dentro del .exe/.app los recursos están en sys._MEIPASS; en desarrollo, junto a este archivo.
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

PRESET_COLORS = ["#FF3B30", "#FF9500", "#FFCC00", "#34C759", "#00C7BE", "#007AFF",
                 "#AF52DE", "#FF2D55", "#FFFFFF"]


# --------------------------------------------------------------------------- tareas en segundo plano

class _Signals(QObject):
    done = Signal(str)
    failed = Signal(str)
    progress = Signal(int, int)


class Job(QRunnable):
    """Ejecuta fn(kb, progress) con el teclado abierto, fuera del hilo de la interfaz."""

    def __init__(self, fn, signals):
        super().__init__()
        self.fn = fn
        # Las señales pertenecen a la ventana: si fueran del Job, Qt las destruiría al
        # terminar y el aviso de "listo" podía perderse, dejando los botones desactivados.
        self.signals = signals
        self.setAutoDelete(False)

    def run(self):
        msgs = []
        try:
            with Keyboard(log=msgs.append) as kb:
                self.fn(kb, self.signals.progress.emit)
            self.signals.done.emit(msgs[-1] if msgs else "Listo.")
        except KeyboardError as e:
            self.signals.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.signals.failed.emit("Error inesperado: %s" % e)


class _StatusSignals(QObject):
    status = Signal(object, object)  # (estado, batería)


def official_driver_running():
    """El driver oficial de Windows interfiere con los comandos si está abierto a la vez."""
    if sys.platform != "win32":
        return False
    import subprocess
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq DeviceDriver.exe", "/NH"],
                             capture_output=True, text=True, timeout=5,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "devicedriver.exe" in out.lower()


def pil_to_pixmap(img, scale=2):
    img = img.convert("RGB")
    q = QImage(img.tobytes(), img.width, img.height, img.width * 3, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(q).scaled(img.width * scale, img.height * scale,
                                       Qt.KeepAspectRatio, Qt.SmoothTransformation)


def slider(lo, hi, value):
    s = QSlider(Qt.Horizontal)
    s.setRange(lo, hi)
    s.setValue(value)
    s.setPageStep(1)
    s.setMinimumWidth(220)
    return s


def slider_with_value(s):
    h = QHBoxLayout()
    h.setSpacing(10)
    val = T.text(str(s.value()), "value")
    s.valueChanged.connect(lambda v: val.setText(str(v)))
    h.addWidget(s)
    h.addWidget(val)
    return h


# --------------------------------------------------------------------------- inicio de sesión

def _launch_command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--tray"]
    return [sys.executable, os.path.abspath(__file__), "--tray"]


def _mac_plist():
    return os.path.expanduser("~/Library/LaunchAgents/com.ajazz.control.plist")


def login_item_enabled():
    if IS_MAC:
        return os.path.exists(_mac_plist())
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k, APP_NAME)
                return True
        except OSError:
            return False
    return False


def set_login_item(on):
    if IS_MAC:
        path = _mac_plist()
        if on:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                plistlib.dump({"Label": "com.ajazz.control", "ProgramArguments": _launch_command(),
                               "RunAtLoad": True}, f)
        elif os.path.exists(path):
            os.remove(path)
    elif sys.platform == "win32":
        import subprocess
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(_launch_command()))
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except OSError:
                    pass


# --------------------------------------------------------------------------- apariencia

def apply_appearance(app, pref):
    """pref: 'system' | 'light' | 'dark'."""
    hints = app.styleHints()
    hints.setColorScheme({"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}
                         .get(pref, Qt.ColorScheme.Unknown))
    dark = hints.colorScheme() == Qt.ColorScheme.Dark
    t = T.DARK if dark else T.LIGHT
    T.current.clear()
    T.current.update(t)
    # Paleta para los diálogos nativos de Qt (selector de color, archivos…).
    pal = QPalette()
    for role, key in [(QPalette.Window, "base"), (QPalette.Base, "base"), (QPalette.AlternateBase, "base"),
                      (QPalette.Button, "base"), (QPalette.WindowText, "text"), (QPalette.Text, "text"),
                      (QPalette.ButtonText, "text"), (QPalette.Highlight, "accent"),
                      (QPalette.HighlightedText, "accent_text"), (QPalette.PlaceholderText, "tertiary")]:
        pal.setColor(role, QColor(t[key]))
    app.setPalette(pal)
    app.setStyleSheet(T.stylesheet(t))
    for w in app.allWidgets():
        if isinstance(w, (T.Toggle, T.Backdrop, T.ScrollEdge)):
            w.update()
        if w.objectName() == "sidebar":
            T.float_shadow(w)


# --------------------------------------------------------------------------- ventana principal

class MainWindow(QMainWindow):
    NAV = [("Reloj", "clock"), ("Luces", "bulb"), ("Pantalla", "photo"), ("Ajustes", "sliders"),
           ("Atajos", "keyboard")]

    def __init__(self, start_hidden=False):
        super().__init__()
        self.settings = QSettings("AJAZZ", "AjazzControl")
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(1)  # nunca dos operaciones HID a la vez
        self.busy_buttons = []
        self._jobs = set()
        self.was_connected = None
        self.state, self.battery = None, None
        self.frames, self.delays, self.preview_i = [], [], 0

        self.setWindowTitle(APP_NAME)
        self.resize(980, 700)
        self.setMinimumSize(820, 560)
        icon = QIcon(os.path.join(HERE, "assets", "icon.png"))
        self.setWindowIcon(icon)

        # barra lateral
        side = QWidget()
        side.setObjectName("sidebar")
        side.setAttribute(Qt.WA_StyledBackground, True)
        side.setFixedWidth(232)
        T.float_shadow(side)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 18, 0, 12)
        sv.setSpacing(10)
        sv.addWidget(T.text(APP_NAME, "appName"))
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setIconSize(T.QSize(24, 24))
        for name, ic in self.NAV:
            QListWidgetItem(T.tile_icon(ic), "  " + name, self.nav)
        sv.addWidget(self.nav, 1)
        self.side_status = T.text("", "sideStatus", wrap=True)
        status_wrap = QHBoxLayout()
        status_wrap.setContentsMargins(12, 0, 12, 0)
        status_wrap.addWidget(self.side_status)
        sv.addLayout(status_wrap)

        self.stack = QStackedWidget()
        for build in (self.build_clock, self.build_lights, self.build_screen, self.build_settings,
                      self.build_shortcuts):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidget(build())
            self.stack.addWidget(scroll)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        # Contenido con difuminado bajo el borde superior (scroll edge effect).
        content = QWidget()
        g = QGridLayout(content)
        g.setContentsMargins(0, 0, 0, 0)
        g.addWidget(self.stack, 0, 0)
        self.edge = T.ScrollEdge(content)
        self.edge.setFixedHeight(26)
        self.edge.hide()
        g.addWidget(self.edge, 0, 0, Qt.AlignTop)
        # Como en macOS, el difuminado solo aparece cuando hay contenido desplazado bajo el borde.
        for i in range(self.stack.count()):
            self.stack.widget(i).verticalScrollBar().valueChanged.connect(lambda *_: self.update_edge())
        self.stack.currentChanged.connect(lambda *_: self.update_edge())

        central = T.Backdrop()
        h = QHBoxLayout(central)
        h.setContentsMargins(10, 10, 0, 10)
        h.setSpacing(0)
        h.addWidget(side)
        h.addWidget(content, 1)
        self.setCentralWidget(central)

        self.build_tray(icon)

        self._status_signals = _StatusSignals(self)
        self._status_signals.status.connect(self.on_status)
        self._status_busy = False
        self._battery_tick = 0
        self.tick = QTimer(self, interval=500, timeout=self.on_tick)
        self.tick.start()
        self.poll = QTimer(self, interval=2500, timeout=self.poll_connection)
        self.poll.start()
        self.on_tick()
        self.poll_connection()
        if not start_hidden:
            self.show()

    def update_edge(self):
        self.edge.setVisible(self.stack.currentWidget().verticalScrollBar().value() > 0)

    # ---- estructura de páginas
    def page(self, title, subtitle=None):
        w = QWidget()
        w.setObjectName("content")
        v = QVBoxLayout(w)
        v.setContentsMargins(34, 22, 34, 30)
        v.setSpacing(24)
        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(T.text(title, "largeTitle"))
        if subtitle:
            head.addWidget(T.text(subtitle, "subtitle", wrap=True))
        v.addLayout(head)
        return w, v

    def primary(self, text, slot):
        b = QPushButton(text)
        b.setObjectName("primary")
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(slot)
        self.busy_buttons.append(b)
        return b

    def secondary(self, text, slot, busy=True):
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(slot)
        if busy:
            self.busy_buttons.append(b)
        return b

    def right_button(self, b):
        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(b)
        return h

    # ---- infraestructura
    def run_job(self, fn, ok_msg=None, on_progress=None, on_end=None, quiet=False):
        if official_driver_running():
            msg = ("El driver oficial de AJAZZ (DeviceDriver.exe) está abierto y le manda sus propios "
                   "comandos al teclado, lo que mezcla los cambios. Ciérralo (también desde la bandeja) "
                   "y vuelve a intentarlo.")
            self.statusBar().showMessage("Cierra el driver oficial de AJAZZ.", 10000)
            if not quiet:
                QMessageBox.warning(self, APP_NAME, msg)
            return
        for b in self.busy_buttons:
            b.setEnabled(False)
        signals = _Signals(self)
        job = Job(fn, signals)
        self._jobs.add(job)
        state = {"finished": False}

        def end():
            if state["finished"]:
                return False
            state["finished"] = True
            self._jobs.discard(job)
            signals.deleteLater()
            for b in self.busy_buttons:
                b.setEnabled(True)
            self.upload_btn.setEnabled(bool(self.frames))
            if on_end:
                on_end()
            return True

        def done(msg):
            if end():
                self.statusBar().showMessage("✓  " + (ok_msg or msg), 6000)

        def failed(msg):
            if end():
                self.statusBar().showMessage(msg, 10000)
                if not quiet:
                    QMessageBox.warning(self, APP_NAME, msg)

        signals.done.connect(done)
        signals.failed.connect(failed)
        if on_progress:
            signals.progress.connect(on_progress)
        # Red de seguridad: si el teclado no contesta nunca, no dejar la ventana bloqueada.
        QTimer.singleShot(180000, self, lambda: failed("El teclado dejó de responder. Desconecta y vuelve "
                                                       "a conectar el cable e inténtalo otra vez."))
        self.pool.start(job)

    def poll_connection(self):
        """Comprueba la conexión (y cada minuto la batería) en un hilo aparte para no trabar la ventana."""
        if self._status_busy:
            return
        self._status_busy = True
        self._battery_tick = (self._battery_tick + 1) % 24  # ~ cada minuto
        want_battery = self._battery_tick == 1 or self.battery is None

        def work():
            try:
                st, addr = connection_state()
            except Exception:  # noqa: BLE001
                st, addr = None, None
            bat = self.battery
            if st == "bluetooth" and want_battery:
                bat = read_battery(addr)
            elif st != "bluetooth":
                bat = None
            self._status_signals.status.emit(st, bat)

        threading.Thread(target=work, daemon=True).start()

    def on_status(self, st, bat):
        self._status_busy = False
        self.state, self.battery = st, bat
        dot = {"cable": T.current["green"], "bluetooth": T.current["accent"]}.get(st, T.current["tertiary"])
        if st == "cable":
            txt = "Conectado por cable"
        elif st == "bluetooth":
            txt = "Bluetooth" + (" · batería %d %%" % bat if bat is not None else "")
        else:
            txt = "Teclado no conectado"
        self.side_status.setText('<span style="color:%s">●</span>&nbsp;&nbsp;%s' % (dot, txt))
        hint = "" if st == "cable" else (
            "Para configurar el teclado conéctalo con el cable USB." if st == "bluetooth" else "")
        self.side_status.setToolTip(hint)
        connected = st == "cable"
        if connected and self.was_connected is False and self.auto_sync.isChecked():
            self.run_job(lambda kb, p: kb.set_time(datetime.now()), "Hora sincronizada al conectar.", quiet=True)
        self.was_connected = connected

    def on_tick(self):
        now = datetime.now()
        self.clock.setText(now.strftime("%H:%M:%S"))
        txt = QLocale.system().toString(QDate.currentDate(), "dddd, d 'de' MMMM 'de' yyyy")
        self.date.setText(txt[:1].upper() + txt[1:])

    # ---- bandeja / barra de menús
    def build_tray(self, icon):
        self.tray = QSystemTrayIcon(icon, self)
        menu = QMenu()
        menu.addAction(QAction("Sincronizar hora", self, triggered=self.sync_now))
        menu.addAction(QAction("Abrir %s" % APP_NAME, self, triggered=self.bring_up))
        menu.addSeparator()
        menu.addAction(QAction("Salir", self, triggered=QApplication.instance().quit))
        self.tray.setContextMenu(menu)
        self.tray.setToolTip(APP_NAME)
        self.tray.activated.connect(lambda r: self.bring_up() if r == QSystemTrayIcon.Trigger and not IS_MAC else None)
        self.tray.show()

    def bring_up(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e):
        if self.auto_sync.isChecked() and self.tray.isVisible():
            self.hide()
            self.tray.showMessage(APP_NAME, "Sigo en segundo plano para sincronizar la hora al conectar el teclado.",
                                  QSystemTrayIcon.Information, 3000)
            e.ignore()
        else:
            QApplication.instance().quit()

    # ---- Reloj
    def build_clock(self):
        w, v = self.page("Reloj", "Pon en hora la pantalla del teclado.")
        self.clock = T.text("", "clock")
        self.clock.setAlignment(Qt.AlignCenter)
        self.date = T.text("", "secondary")
        self.date.setAlignment(Qt.AlignCenter)
        sync = self.primary("Sincronizar con este equipo", self.sync_now)
        hero = QVBoxLayout()
        hero.setContentsMargins(10, 18, 10, 8)
        hero.setSpacing(4)
        hero.addWidget(self.clock)
        hero.addWidget(self.date)
        hero.addSpacing(14)
        hero.addLayout(self.right_button_center(sync))
        v.addWidget(T.group(hero, padded=True,
                            footer="Necesita el cable USB. Por Bluetooth o 2.4G el teclado no acepta la hora."))

        self.manual = QDateTimeEdit(QDateTime.currentDateTime())
        self.manual.setDisplayFormat("dd/MM/yyyy  HH:mm:ss")
        self.manual.setCalendarPopup(True)
        send_manual = self.secondary("Enviar", self.sync_manual)
        ctl = QHBoxLayout()
        ctl.setSpacing(8)
        ctl.addWidget(self.manual)
        ctl.addWidget(send_manual)
        v.addWidget(T.group(T.row("Fecha y hora", ctl), header="Hora personalizada"))

        self.auto_sync = T.Toggle(self.settings.value("auto_sync", True, bool))
        self.auto_sync.toggled.connect(lambda on: self.settings.setValue("auto_sync", on))
        self.login = T.Toggle(login_item_enabled())
        self.login.toggled.connect(self.toggle_login)
        v.addWidget(T.group(
            T.row("Sincronizar al conectar el cable", self.auto_sync,
                  "Pone la hora sola cada vez que enchufas el teclado, por ejemplo al cargarlo."),
            T.row("Abrir al iniciar sesión", self.login, "Se queda en segundo plano, en la barra de menús."),
            header="Automático"))
        v.addStretch()
        return w

    def right_button_center(self, b):
        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(b)
        h.addStretch()
        return h

    def sync_now(self):
        self.run_job(lambda kb, p: kb.set_time(datetime.now()))

    def sync_manual(self):
        t = self.manual.dateTime().toPython()
        self.run_job(lambda kb, p: kb.set_time(t))

    def toggle_login(self, on):
        try:
            set_login_item(on)
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, "No se pudo cambiar el inicio automático: %s" % e)

    # ---- Luces
    def build_lights(self):
        w, v = self.page("Luces", "Elige un efecto y pulsa Aplicar.")
        grid = QGridLayout()
        grid.setSpacing(8)
        self.effect_group = QButtonGroup(self)
        effects = [e for e in P.Effect if e != P.Effect.OFF] + [P.Effect.OFF]
        for i, e in enumerate(effects):
            b = QPushButton(P.EFFECT_NAMES[e])
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setMinimumHeight(34)
            b.setCursor(Qt.PointingHandCursor)
            self.effect_group.addButton(b, int(e))
            grid.addWidget(b, i // 4, i % 4)
        last = self.settings.value("light/effect", int(P.Effect.STATIC), int)
        (self.effect_group.button(last) or self.effect_group.button(1)).setChecked(True)
        self.effect_group.idToggled.connect(lambda *_: self.update_light_controls())
        v.addWidget(T.group(grid, header="Efecto", padded=True))

        # color
        self.color = QColor(self.settings.value("light/color", "#007AFF"))
        self.color_mode = T.Segmented([("Un color", True), ("Multicolor", False)],
                                      self.settings.value("light/use_color", True, bool))
        self.color_mode.changed.connect(lambda *_: self.update_light_controls())
        sw = QHBoxLayout()
        sw.setSpacing(8)
        self.swatch_group = QButtonGroup(self)
        for c in PRESET_COLORS:
            s = QPushButton()
            s.setCheckable(True)
            s.setFixedSize(26, 26)
            s.setCursor(Qt.PointingHandCursor)
            s.setProperty("hex", c)
            s.clicked.connect(lambda _=False, c=c: self.set_color(QColor(c)))
            self.swatch_group.addButton(s)
            sw.addWidget(s)
        self.custom_color = QPushButton("Otro…")
        self.custom_color.setCursor(Qt.PointingHandCursor)
        self.custom_color.clicked.connect(self.pick_color)
        sw.addSpacing(6)
        sw.addWidget(self.custom_color)
        self.swatch_row = T.row("Color", sw)
        self.brightness = slider(1, P.MAX_BRIGHTNESS, self.settings.value("light/brightness", 5, int))
        self.speed = slider(0, P.MAX_SPEED, self.settings.value("light/speed", 3, int))
        self.direction = T.Segmented([("Izquierda", P.Direction.LEFT), ("Derecha", P.Direction.RIGHT)])
        self.dir_host = QHBoxLayout()
        self.dir_host.addWidget(self.direction)
        self.dir_row = T.row("Dirección", self.dir_host)
        v.addWidget(T.group(
            T.row("Modo de color", self.color_mode),
            self.swatch_row,
            T.row("Brillo", slider_with_value(self.brightness)),
            T.row("Velocidad", slider_with_value(self.speed)),
            self.dir_row,
            header="Ajustes del efecto",
            footer="¿No se encienden? Puede que estén apagadas desde el teclado: pulsa Fn + X."))
        v.addLayout(self.right_button(self.primary("Aplicar luces", self.apply_lights)))
        v.addStretch()
        self.set_color(self.color, select_mode=False)
        self.update_light_controls()
        return w

    def set_color(self, c, select_mode=True):
        self.color = c
        ring = T.current["text"]
        for b in self.swatch_group.buttons():
            hexc = b.property("hex")
            sel = QColor(hexc).name().lower() == c.name().lower()
            b.setChecked(sel)
            b.setStyleSheet("QPushButton{background:%s;border-radius:13px;border:%s;padding:0;min-height:0;min-width:0;}"
                            % (hexc, ("2px solid %s" % ring) if sel else "1px solid rgba(0,0,0,0.12)"))
        custom = not any(b.isChecked() for b in self.swatch_group.buttons())
        self.custom_color.setStyleSheet(
            "QPushButton{border:2px solid %s;}" % c.name() if custom else "")
        if select_mode:
            self.color_mode.set_data(True)
            self.update_light_controls()

    def pick_color(self):
        c = QColorDialog.getColor(self.color, self, "Color de las luces")
        if c.isValid():
            self.set_color(c)

    def update_light_controls(self):
        e = P.Effect(self.effect_group.checkedId())
        on = self.color_mode.data() is True
        self.swatch_row.setEnabled(on)
        fx = QGraphicsOpacityEffect(self.swatch_row)
        fx.setOpacity(1.0 if on else 0.35)
        self.swatch_row.setGraphicsEffect(fx)
        dirs = P.EFFECT_DIRECTIONS.get(e, ())
        names = {P.Direction.LEFT: "Izquierda", P.Direction.RIGHT: "Derecha",
                 P.Direction.UP: "Arriba", P.Direction.DOWN: "Abajo"}
        old = self.direction.data()
        self.dir_host.removeWidget(self.direction)
        self.direction.deleteLater()
        self.direction = T.Segmented([(names[d], d) for d in dirs] or [("—", P.Direction.LEFT)],
                                     old if old in dirs else None)
        self.dir_host.addWidget(self.direction)
        self.dir_row.setVisible(bool(dirs))

    def apply_lights(self):
        e = P.Effect(self.effect_group.checkedId())
        l = P.Lighting(
            effect=e,
            color=(self.color.red(), self.color.green(), self.color.blue()),
            custom_color=self.color_mode.data() is True,
            brightness=self.brightness.value(),
            speed=self.speed.value(),
            direction=P.Direction(self.direction.data() or 0),
        )
        s = self.settings
        s.setValue("light/effect", int(e))
        s.setValue("light/color", self.color.name())
        s.setValue("light/use_color", l.custom_color)
        s.setValue("light/brightness", l.brightness)
        s.setValue("light/speed", l.speed)
        self.run_job(lambda kb, p: kb.set_lighting(l), "Luces aplicadas: %s." % P.EFFECT_NAMES[e])

    # ---- Pantalla
    def build_screen(self):
        w, v = self.page("Pantalla", "Sube una imagen o un GIF animado a la pantalla del teclado.")
        self.preview = QLabel("Sin imagen")
        self.preview.setObjectName("preview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedSize(P.SCREEN_W * 2 + 12, P.SCREEN_H * 2 + 12)
        self.preview_info = T.text("160 × 96 píxeles · hasta 255 cuadros", "secondary")
        self.preview_info.setAlignment(Qt.AlignCenter)
        choose = self.secondary("Elegir imagen o GIF…", self.choose_image)
        prev = QVBoxLayout()
        prev.setSpacing(10)
        prev.addWidget(self.preview, 0, Qt.AlignHCenter)
        prev.addWidget(self.preview_info)
        prev.addLayout(self.right_button_center(choose))
        v.addWidget(T.group(prev, padded=True))

        self.fit_mode = T.Segmented([("Llenar", "fill"), ("Encajar", "fit"), ("Estirar", "stretch")])
        self.fit_mode.changed.connect(lambda *_: self.reload_image())
        self.fixed_delay = T.Toggle(False)
        self.delay_ms = QSpinBox()
        self.delay_ms.setRange(P.MIN_DELAY_MS, P.MAX_DELAY_MS)
        self.delay_ms.setSingleStep(10)
        self.delay_ms.setValue(100)
        self.delay_ms.setSuffix(" ms")
        self.delay_ms.setEnabled(False)
        self.fixed_delay.toggled.connect(self.delay_ms.setEnabled)
        self.fixed_delay.toggled.connect(lambda *_: self.next_preview_frame())
        speed = QHBoxLayout()
        speed.setSpacing(10)
        speed.addWidget(self.delay_ms)
        speed.addWidget(self.fixed_delay)
        v.addWidget(T.group(
            T.row("Ajuste", self.fit_mode, "Llenar recorta los bordes; Encajar deja franjas negras."),
            T.row("Velocidad fija", speed, "Ignora la velocidad del GIF y usa este tiempo por cuadro."),
            header="Opciones",
            footer="Subir una imagen reemplaza la animación actual. Para ver solo el reloj y el estado, "
                   "oculta la animación con Fn + Supr en el teclado."))

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        v.addWidget(self.progress)
        self.upload_btn = self.primary("Subir a la pantalla", self.upload_image)
        self.upload_btn.setEnabled(False)
        v.addLayout(self.right_button(self.upload_btn))
        v.addStretch()

        self.image_path = None
        self.anim = QTimer(self, timeout=self.next_preview_frame)
        return w

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Elegir imagen", self.settings.value("screen/dir", ""),
                                              "Imágenes (*.gif *.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self.settings.setValue("screen/dir", os.path.dirname(path))
            self.image_path = path
            self.reload_image()

    def reload_image(self):
        if not self.image_path:
            return
        try:
            self.frames, self.delays = screen.load_frames(self.image_path, self.fit_mode.data())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, APP_NAME, "No se pudo abrir la imagen: %s" % e)
            return
        self.pixmaps = [pil_to_pixmap(f) for f in self.frames]
        self.preview_i = 0
        n = len(self.frames)
        self.preview_info.setText("%s · %d cuadro%s" % (os.path.basename(self.image_path), n, "" if n == 1 else "s"))
        self.upload_btn.setEnabled(n > 0)
        self.next_preview_frame()

    def current_delays(self):
        if self.fixed_delay.isChecked():
            return [self.delay_ms.value()] * len(self.frames)
        return self.delays

    def next_preview_frame(self):
        if not self.frames:
            return
        self.preview_i %= len(self.frames)
        self.preview.setPixmap(self.pixmaps[self.preview_i])
        delay = self.current_delays()[self.preview_i]
        self.preview_i = (self.preview_i + 1) % len(self.frames)
        if len(self.frames) > 1:
            self.anim.start(delay)
        else:
            self.anim.stop()

    def upload_image(self):
        frames = [screen.to_rgb565(f) for f in self.frames]
        delays = self.current_delays()
        self.progress.setValue(0)
        self.progress.setVisible(True)

        def prog(i, n):
            self.progress.setMaximum(n)
            self.progress.setValue(i)

        self.run_job(lambda kb, p: kb.upload_animation(frames, delays, p), "Imagen subida a la pantalla.",
                     on_progress=prog, on_end=lambda: self.progress.setVisible(False))

    # ---- Ajustes
    def build_settings(self):
        w, v = self.page("Ajustes")
        self.appearance = T.Segmented([("Sistema", "system"), ("Claro", "light"), ("Oscuro", "dark")],
                                      self.settings.value("appearance", "system"))
        self.appearance.changed.connect(self.change_appearance)
        v.addWidget(T.group(T.row("Apariencia", self.appearance, "Sistema sigue el modo claro u oscuro de tu equipo."),
                            header="Aplicación"))

        self.sleep = QComboBox()
        for s in P.Sleep:
            self.sleep.addItem(P.SLEEP_NAMES[s], int(s))
        self.sleep.setCurrentIndex(self.sleep.findData(self.settings.value("set/sleep", int(P.Sleep.MIN_5), int)))
        self.response = slider(1, 5, self.settings.value("set/response", 2, int))
        self.game = T.Toggle(self.settings.value("set/game", False, bool))
        self.block_win = T.Toggle(self.settings.value("set/win", False, bool))
        self.block_f4 = T.Toggle(self.settings.value("set/f4", False, bool))
        self.block_tab = T.Toggle(self.settings.value("set/tab", False, bool))
        subs = [T.row("Bloquear tecla %s" % ("Cmd / Windows" if IS_MAC else "Windows"), self.block_win),
                T.row("Bloquear Alt + F4", self.block_f4),
                T.row("Bloquear Alt + Tab", self.block_tab)]
        for r in subs:
            r.layout().setContentsMargins(34, 9, 12, 9)
        self.game.toggled.connect(lambda on: [r.setEnabled(on) for r in subs])
        self.game.toggled.emit(self.game.isChecked())

        v.addWidget(T.group(
            T.row("Apagar luces tras inactividad", self.sleep),
            T.row("Tiempo de respuesta de teclas", slider_with_value(self.response),
                  "1 = más rápido · 5 = más estable (evita dobles pulsaciones)."),
            header="Teclado"))
        v.addWidget(T.group(T.row("Modo juego", self.game, "Evita salir del juego por accidente."), *subs,
                            header="Modo juego",
                            footer="Estos ajustes se guardan en el propio teclado."))
        v.addLayout(self.right_button(self.primary("Guardar en el teclado", self.apply_settings)))
        v.addStretch()
        v.addWidget(T.text("%s %s · protocolo extraído del driver oficial de AJAZZ" % (APP_NAME, __version__),
                           "footnote"), 0, Qt.AlignHCenter)
        return w

    def change_appearance(self, pref):
        self.settings.setValue("appearance", pref)
        apply_appearance(QApplication.instance(), pref)
        self.set_color(self.color, select_mode=False)
        self.on_status(self.state, self.battery)

    def apply_settings(self):
        s = P.Settings(
            game_mode=self.game.isChecked(),
            block_alt_tab=self.block_tab.isChecked(),
            block_alt_f4=self.block_f4.isChecked(),
            block_win=self.block_win.isChecked(),
            light_sleep=P.Sleep(self.sleep.currentData()),
            key_response=self.response.value(),
        )
        st = self.settings
        st.setValue("set/sleep", int(s.light_sleep))
        st.setValue("set/response", s.key_response)
        for key, val in [("game", s.game_mode), ("win", s.block_win), ("f4", s.block_alt_f4), ("tab", s.block_alt_tab)]:
            st.setValue("set/" + key, val)
        self.run_job(lambda kb, p: kb.set_settings(s), "Ajustes guardados en el teclado.")

    # ---- Atajos
    SHORTCUTS = [
        ("Pantalla", [
            (["Fn", "Supr"], "Mostrar u ocultar la animación (sin ella se ven el reloj y el estado)"),
            (["Fn", "Insert"], "Encender o apagar la pantalla"),
            (["Fn", "Re Pág"], "Moverse a la izquierda en el menú de la pantalla"),
            (["Fn", "Av Pág"], "Moverse a la derecha en el menú de la pantalla"),
            (["Fn", "Enter"], "Confirmar la opción elegida"),
        ]),
        ("Luces", [
            (["Fn", "X"], "Encender o apagar las luces"),
            (["Fn", "|"], "Cambiar entre los 20 efectos"),
            (["Fn", "↑"], "Subir brillo (5 niveles)"),
            (["Fn", "↓"], "Bajar brillo"),
            (["Fn", "→"], "Cambiar el color"),
            (["Fn", "←"], "Cambiar la dirección del efecto"),
            (["Fn", "="], "Más velocidad"),
            (["Fn", "-"], "Menos velocidad"),
        ]),
        ("Modos de luz para juegos", [
            (["Fn", "1"], "Modo FPS"),
            (["Fn", "2"], "Modo LOL"),
            (["Fn", "3"], "Modo oficina"),
            (["Fn", "~"], "Grabar tu propio modo de luces"),
        ]),
        ("Conexión", [
            (["Fn", "Q"], "Bluetooth 1 (mantén 3 s para emparejar)"),
            (["Fn", "W"], "Bluetooth 2 (mantén 3 s para emparejar)"),
            (["Fn", "E"], "Bluetooth 3 (mantén 3 s para emparejar)"),
            (["Fn", "R"], "Receptor 2.4G (mantén 3 s para emparejar)"),
        ]),
        ("Sistema", [
            (["Fn", "Espacio"], "Mantén 3-5 s para restaurar de fábrica"),
        ]),
    ]

    def build_shortcuts(self):
        w, v = self.page("Atajos", "Funcionan directamente en el teclado, sin la app (según el manual del AK832 Pro).")
        for title, items in self.SHORTCUTS:
            rows = []
            for keys, desc in items:
                combo = QHBoxLayout()
                combo.setSpacing(4)
                for i, k in enumerate(keys):
                    if i:
                        combo.addWidget(T.text("+", "secondary"))
                    combo.addWidget(T.text(k, "keycap"))
                rows.append(T.row(desc, combo))
            v.addWidget(T.group(*rows, header=title))
        v.addStretch()
        return w


def main():
    if sys.platform == "win32":
        # Sin esto Windows agrupa la ventana bajo python.exe y muestra un ícono genérico.
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AJAZZ.Control")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(os.path.join(HERE, "assets", "icon.png")))
    app.setQuitOnLastWindowClosed(False)
    if sys.platform == "win32":
        f = QFont("Segoe UI Variable Text")
        if not f.exactMatch():
            f = QFont("Segoe UI")
        f.setPointSizeF(9.5)
        app.setFont(f)
    settings = QSettings("AJAZZ", "AjazzControl")
    apply_appearance(app, settings.value("appearance", "system"))

    busy = {"on": False}

    def system_changed(*_):
        if busy["on"]:
            return
        if settings.value("appearance", "system") == "system":
            busy["on"] = True
            apply_appearance(app, "system")
            win.set_color(win.color, select_mode=False)
            win.on_status(win.state, win.battery)
            busy["on"] = False

    app.styleHints().colorSchemeChanged.connect(system_changed)
    win = MainWindow(start_hidden="--tray" in sys.argv)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
