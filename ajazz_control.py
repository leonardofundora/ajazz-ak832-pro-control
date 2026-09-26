"""AJAZZ Control: clock, lights, screen and settings for the AK832 Pro on macOS and Windows."""

import os
import plistlib
import sys
import threading
import traceback
from datetime import datetime

from PySide6.QtCore import QDate, QDateTime, QLocale, QObject, QRunnable, QSettings, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QImage, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QColorDialog, QComboBox, QDateTimeEdit, QFileDialog, QFrame,
    QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSlider, QSpinBox, QStackedWidget, QSystemTrayIcon,
    QVBoxLayout, QWidget,
)

import ui_theme as T
from ak832 import __version__
from ak832 import i18n
from ak832 import protocol as P
from ak832 import screen
from ak832.battery import read_battery
from ak832.device import Keyboard, KeyboardError, connection_state
from ak832.i18n import tr

APP_NAME = "AJAZZ Control"
IS_MAC = sys.platform == "darwin"
# Inside the bundled .exe/.app resources live in sys._MEIPASS; in development, next to this file.
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

PRESET_COLORS = ["#FF3B30", "#FF9500", "#FFCC00", "#34C759", "#00C7BE", "#007AFF",
                 "#AF52DE", "#FF2D55", "#FFFFFF"]


# --------------------------------------------------------------------------- background jobs

class _Signals(QObject):
    done = Signal(str)
    failed = Signal(str)
    progress = Signal(int, int)


class Job(QRunnable):
    """Runs fn(kb, progress) with the keyboard open, off the UI thread."""

    def __init__(self, fn, signals):
        super().__init__()
        self.fn = fn
        # The signals belong to the window: if they belonged to the Job, Qt would destroy them
        # when it finishes and the "done" notification could get lost, leaving buttons disabled.
        self.signals = signals
        self.setAutoDelete(False)

    def run(self):
        msgs = []
        try:
            with Keyboard(log=msgs.append) as kb:
                self.fn(kb, self.signals.progress.emit)
            self.signals.done.emit(msgs[-1] if msgs else tr("Done."))
        except KeyboardError as e:
            self.signals.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.signals.failed.emit(tr("Unexpected error: %s", e))


class _StatusSignals(QObject):
    status = Signal(object, object)  # (state, battery)


def official_driver_running():
    """The official Windows driver interferes with the commands if it's open at the same time."""
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


# --------------------------------------------------------------------------- open at login

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


# --------------------------------------------------------------------------- appearance

def apply_appearance(app, pref):
    """pref: 'system' | 'light' | 'dark'."""
    hints = app.styleHints()
    hints.setColorScheme({"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}
                         .get(pref, Qt.ColorScheme.Unknown))
    dark = hints.colorScheme() == Qt.ColorScheme.Dark
    t = T.DARK if dark else T.LIGHT
    T.current.clear()
    T.current.update(t)
    # Palette for Qt's own dialogs (color picker, file chooser…).
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


# --------------------------------------------------------------------------- main window

class MainWindow(QMainWindow):
    NAV = [("Clock", "clock"), ("Lights", "bulb"), ("Screen", "photo"), ("Settings", "sliders"),
           ("Shortcuts", "keyboard")]

    def __init__(self, controller, start_hidden=False):
        super().__init__()
        self.controller = controller
        self.settings = QSettings("AJAZZ", "AjazzControl")
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(1)  # never two HID operations at once
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

        # floating sidebar
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
            QListWidgetItem(T.tile_icon(ic), "  " + tr(name), self.nav)
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

        # Content with a soft fade under the top edge (scroll edge effect).
        content = QWidget()
        g = QGridLayout(content)
        g.setContentsMargins(0, 0, 0, 0)
        g.addWidget(self.stack, 0, 0)
        self.edge = T.ScrollEdge(content)
        self.edge.setFixedHeight(26)
        self.edge.hide()
        g.addWidget(self.edge, 0, 0, Qt.AlignTop)
        # Like on macOS, the fade only shows when content is scrolled under the edge.
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

    def shutdown(self):
        """Stops timers and removes the tray icon (used when the window is rebuilt)."""
        self.tick.stop()
        self.poll.stop()
        self.anim.stop()
        self.tray.hide()

    # ---- page structure
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

    def center_button(self, b):
        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(b)
        h.addStretch()
        return h

    # ---- infrastructure
    def run_job(self, fn, ok_msg=None, on_progress=None, on_end=None, quiet=False):
        if official_driver_running():
            self.statusBar().showMessage(tr("Close the official AJAZZ driver."), 10000)
            if not quiet:
                QMessageBox.warning(self, APP_NAME, tr(
                    "The official AJAZZ driver (DeviceDriver.exe) is open and sends its own commands to the "
                    "keyboard, which mixes up the changes. Close it (also from the system tray) and try again."))
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
        # Safety net: if the keyboard never answers, don't leave the window locked.
        QTimer.singleShot(180000, self, lambda: failed(
            tr("The keyboard stopped responding. Unplug and reconnect the cable and try again.")))
        self.pool.start(job)

    def poll_connection(self):
        """Checks the connection (and about once a minute the battery) on a thread, to keep the UI smooth."""
        if self._status_busy:
            return
        self._status_busy = True
        self._battery_tick = (self._battery_tick + 1) % 24  # ~ once a minute
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
            txt = tr("Connected by cable")
        elif st == "bluetooth":
            txt = tr("Bluetooth") + (tr(" · battery %d %%", bat) if bat is not None else "")
        else:
            txt = tr("Keyboard not connected")
        self.side_status.setText('<span style="color:%s">●</span>&nbsp;&nbsp;%s' % (dot, txt))
        self.side_status.setToolTip(tr("To configure the keyboard, connect it with the USB cable.")
                                    if st == "bluetooth" else "")
        connected = st == "cable"
        if connected and self.was_connected is False and self.auto_sync.isChecked():
            self.run_job(lambda kb, p: kb.set_time(datetime.now()), tr("Time synced on connect."), quiet=True)
        self.was_connected = connected

    def on_tick(self):
        now = datetime.now()
        self.clock.setText(now.strftime("%H:%M:%S"))
        loc = QLocale(QLocale.Spanish if i18n.language() == "es" else QLocale.English)
        txt = loc.toString(QDate.currentDate(), tr("dddd, MMMM d, yyyy"))
        self.date.setText(txt[:1].upper() + txt[1:])

    # ---- tray / menu bar
    def build_tray(self, icon):
        self.tray = QSystemTrayIcon(icon, self)
        menu = QMenu(self)
        menu.addAction(QAction(tr("Sync time"), self, triggered=self.sync_now))
        menu.addAction(QAction(tr("Open %s", APP_NAME), self, triggered=self.bring_up))
        menu.addSeparator()
        menu.addAction(QAction(tr("Quit"), self, triggered=QApplication.instance().quit))
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
            self.tray.showMessage(APP_NAME, tr("Still running in the background to sync the time when the "
                                               "keyboard is connected."), QSystemTrayIcon.Information, 3000)
            e.ignore()
        else:
            QApplication.instance().quit()

    # ---- Clock
    def build_clock(self):
        w, v = self.page(tr("Clock"), tr("Set the time on the keyboard's screen."))
        self.clock = T.text("", "clock")
        self.clock.setAlignment(Qt.AlignCenter)
        self.date = T.text("", "secondary")
        self.date.setAlignment(Qt.AlignCenter)
        sync = self.primary(tr("Sync with this computer"), self.sync_now)
        hero = QVBoxLayout()
        hero.setContentsMargins(10, 18, 10, 8)
        hero.setSpacing(4)
        hero.addWidget(self.clock)
        hero.addWidget(self.date)
        hero.addSpacing(14)
        hero.addLayout(self.center_button(sync))
        v.addWidget(T.group(hero, padded=True, footer=tr(
            "Requires the USB cable. Over Bluetooth or 2.4G the keyboard doesn't accept the time.")))

        self.manual = QDateTimeEdit(QDateTime.currentDateTime())
        self.manual.setDisplayFormat("dd/MM/yyyy  HH:mm:ss" if i18n.language() == "es" else "yyyy-MM-dd  HH:mm:ss")
        self.manual.setCalendarPopup(True)
        send_manual = self.secondary(tr("Send"), self.sync_manual)
        ctl = QHBoxLayout()
        ctl.setSpacing(8)
        ctl.addWidget(self.manual)
        ctl.addWidget(send_manual)
        v.addWidget(T.group(T.row(tr("Date and time"), ctl), header=tr("Custom time")))

        self.auto_sync = T.Toggle(self.settings.value("auto_sync", True, bool))
        self.auto_sync.toggled.connect(lambda on: self.settings.setValue("auto_sync", on))
        self.login = T.Toggle(login_item_enabled())
        self.login.toggled.connect(self.toggle_login)
        v.addWidget(T.group(
            T.row(tr("Sync when the cable is connected"), self.auto_sync,
                  tr("Sets the time automatically every time you plug in the keyboard, for example to charge it.")),
            T.row(tr("Open at login"), self.login, tr("Stays in the background, in the menu bar.")),
            header=tr("Automatic")))
        v.addStretch()
        return w

    def sync_now(self):
        self.run_job(lambda kb, p: kb.set_time(datetime.now()))

    def sync_manual(self):
        t = self.manual.dateTime().toPython()
        self.run_job(lambda kb, p: kb.set_time(t))

    def toggle_login(self, on):
        try:
            set_login_item(on)
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, tr("Couldn't change the startup setting: %s", e))

    # ---- Lights
    DIRECTION_NAMES = {P.Direction.LEFT: "Left", P.Direction.RIGHT: "Right",
                       P.Direction.UP: "Up", P.Direction.DOWN: "Down"}

    def build_lights(self):
        w, v = self.page(tr("Lights"), tr("Pick an effect and press Apply."))
        grid = QGridLayout()
        grid.setSpacing(8)
        self.effect_group = QButtonGroup(self)
        effects = [e for e in P.Effect if e != P.Effect.OFF] + [P.Effect.OFF]
        for i, e in enumerate(effects):
            b = QPushButton(P.effect_name(e))
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setMinimumHeight(34)
            b.setCursor(Qt.PointingHandCursor)
            self.effect_group.addButton(b, int(e))
            grid.addWidget(b, i // 4, i % 4)
        last = self.settings.value("light/effect", int(P.Effect.STATIC), int)
        (self.effect_group.button(last) or self.effect_group.button(1)).setChecked(True)
        self.effect_group.idToggled.connect(lambda *_: self.update_light_controls())
        v.addWidget(T.group(grid, header=tr("Effect"), padded=True))

        self.color = QColor(self.settings.value("light/color", "#007AFF"))
        self.color_mode = T.Segmented([(tr("One color"), True), (tr("Multicolor"), False)],
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
        self.custom_color = QPushButton(tr("Other…"))
        self.custom_color.setCursor(Qt.PointingHandCursor)
        self.custom_color.clicked.connect(self.pick_color)
        sw.addSpacing(6)
        sw.addWidget(self.custom_color)
        self.swatch_row = T.row(tr("Color"), sw)
        self.brightness = slider(1, P.MAX_BRIGHTNESS, self.settings.value("light/brightness", 5, int))
        self.speed = slider(0, P.MAX_SPEED, self.settings.value("light/speed", 3, int))
        self.direction = T.Segmented([(tr("Left"), P.Direction.LEFT), (tr("Right"), P.Direction.RIGHT)])
        self.dir_host = QHBoxLayout()
        self.dir_host.addWidget(self.direction)
        self.dir_row = T.row(tr("Direction"), self.dir_host)
        v.addWidget(T.group(
            T.row(tr("Color mode"), self.color_mode),
            self.swatch_row,
            T.row(tr("Brightness"), slider_with_value(self.brightness)),
            T.row(tr("Speed"), slider_with_value(self.speed)),
            self.dir_row,
            header=tr("Effect settings"),
            footer=tr("Lights won't turn on? They may be off from the keyboard itself: press Fn + X.")))
        v.addLayout(self.right_button(self.primary(tr("Apply lights"), self.apply_lights)))
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
        self.custom_color.setStyleSheet("QPushButton{border:2px solid %s;}" % c.name() if custom else "")
        if select_mode:
            self.color_mode.set_data(True)
            self.update_light_controls()

    def pick_color(self):
        c = QColorDialog.getColor(self.color, self, tr("Light color"))
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
        old = self.direction.data()
        self.dir_host.removeWidget(self.direction)
        self.direction.deleteLater()
        self.direction = T.Segmented([(tr(self.DIRECTION_NAMES[d]), d) for d in dirs] or [("—", P.Direction.LEFT)],
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
        self.run_job(lambda kb, p: kb.set_lighting(l), tr("Lights applied: %s.", P.effect_name(e)))

    # ---- Screen
    def build_screen(self):
        w, v = self.page(tr("Screen"), tr("Upload an image or an animated GIF to the keyboard's screen."))
        self.preview = QLabel(tr("No image"))
        self.preview.setObjectName("preview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedSize(P.SCREEN_W * 2 + 12, P.SCREEN_H * 2 + 12)
        self.preview_info = T.text(tr("160 × 96 pixels · up to 255 frames"), "secondary")
        self.preview_info.setAlignment(Qt.AlignCenter)
        choose = self.secondary(tr("Choose image or GIF…"), self.choose_image)
        prev = QVBoxLayout()
        prev.setSpacing(10)
        prev.addWidget(self.preview, 0, Qt.AlignHCenter)
        prev.addWidget(self.preview_info)
        prev.addLayout(self.center_button(choose))
        v.addWidget(T.group(prev, padded=True))

        self.fit_mode = T.Segmented([(tr("Fill"), "fill"), (tr("Fit"), "fit"), (tr("Stretch"), "stretch")])
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
            T.row(tr("Scaling"), self.fit_mode, tr("Fill crops the edges; Fit adds black bars.")),
            T.row(tr("Fixed speed"), speed, tr("Ignores the GIF's own timing and uses this time per frame.")),
            header=tr("Options"),
            footer=tr("Uploading an image replaces the current animation. To see only the clock and status, "
                      "hide the animation with Fn + Del on the keyboard.")))

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        v.addWidget(self.progress)
        self.upload_btn = self.primary(tr("Upload to screen"), self.upload_image)
        self.upload_btn.setEnabled(False)
        v.addLayout(self.right_button(self.upload_btn))
        v.addStretch()

        self.image_path = None
        self.anim = QTimer(self, timeout=self.next_preview_frame)
        return w

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Choose image"), self.settings.value("screen/dir", ""),
                                              tr("Images (*.gif *.png *.jpg *.jpeg *.webp *.bmp)"))
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
            QMessageBox.warning(self, APP_NAME, tr("Couldn't open the image: %s", e))
            return
        self.pixmaps = [pil_to_pixmap(f) for f in self.frames]
        self.preview_i = 0
        n = len(self.frames)
        self.preview_info.setText(tr("%s · %d frame" if n == 1 else "%s · %d frames",
                                     os.path.basename(self.image_path), n))
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

        self.run_job(lambda kb, p: kb.upload_animation(frames, delays, p), tr("Image uploaded to the screen."),
                     on_progress=prog, on_end=lambda: self.progress.setVisible(False))

    # ---- Settings
    def build_settings(self):
        w, v = self.page(tr("Settings"))
        self.appearance = T.Segmented([(tr("System"), "system"), (tr("Light"), "light"), (tr("Dark"), "dark")],
                                      self.settings.value("appearance", "system"))
        self.appearance.changed.connect(self.change_appearance)
        # Language names are always shown in their own language.
        self.lang = T.Segmented([(tr("System"), "system"), ("English", "en"), ("Español", "es")],
                                self.settings.value("language", "system"))
        self.lang.changed.connect(self.change_language)
        v.addWidget(T.group(
            T.row(tr("Appearance"), self.appearance, tr("System follows your computer's light or dark mode.")),
            T.row(tr("Language"), self.lang, tr("System uses your computer's language.")),
            header=tr("App")))

        self.sleep = QComboBox()
        for s in P.Sleep:
            self.sleep.addItem(P.sleep_name(s), int(s))
        self.sleep.setCurrentIndex(self.sleep.findData(self.settings.value("set/sleep", int(P.Sleep.MIN_5), int)))
        self.response = slider(1, 5, self.settings.value("set/response", 2, int))
        self.game = T.Toggle(self.settings.value("set/game", False, bool))
        self.block_win = T.Toggle(self.settings.value("set/win", False, bool))
        self.block_f4 = T.Toggle(self.settings.value("set/f4", False, bool))
        self.block_tab = T.Toggle(self.settings.value("set/tab", False, bool))
        subs = [T.row(tr("Block %s key", tr("Cmd / Windows") if IS_MAC else tr("Windows")), self.block_win),
                T.row(tr("Block Alt + F4"), self.block_f4),
                T.row(tr("Block Alt + Tab"), self.block_tab)]
        for r in subs:
            r.layout().setContentsMargins(34, 9, 12, 9)
        self.game.toggled.connect(lambda on: [r.setEnabled(on) for r in subs])
        self.game.toggled.emit(self.game.isChecked())

        v.addWidget(T.group(
            T.row(tr("Turn lights off when idle"), self.sleep),
            T.row(tr("Key response time"), slider_with_value(self.response),
                  tr("1 = fastest · 5 = most stable (avoids double presses).")),
            header=tr("Keyboard")))
        v.addWidget(T.group(T.row(tr("Game mode"), self.game, tr("Prevents leaving your game by accident.")), *subs,
                            header=tr("Game mode"),
                            footer=tr("These settings are stored on the keyboard itself.")))
        v.addLayout(self.right_button(self.primary(tr("Save to keyboard"), self.apply_settings)))
        v.addStretch()
        v.addWidget(T.text(tr("%s %s · protocol extracted from the official AJAZZ driver", APP_NAME, __version__),
                           "footnote"), 0, Qt.AlignHCenter)
        return w

    def change_appearance(self, pref):
        self.settings.setValue("appearance", pref)
        apply_appearance(QApplication.instance(), pref)
        self.set_color(self.color, select_mode=False)
        self.on_status(self.state, self.battery)

    def change_language(self, pref):
        self.settings.setValue("language", pref)
        i18n.set_language(pref)
        self.controller.rebuild(page=self.nav.currentRow())

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
        self.run_job(lambda kb, p: kb.set_settings(s), tr("Settings saved to the keyboard."))

    # ---- Shortcuts
    SHORTCUTS = [
        ("Screen", [
            (["Fn", "Del"], "Show or hide the animation (without it you see the clock and status)"),
            (["Fn", "Insert"], "Turn the screen on or off"),
            (["Fn", "PgUp"], "Move left in the screen menu"),
            (["Fn", "PgDn"], "Move right in the screen menu"),
            (["Fn", "Enter"], "Confirm the selected option"),
        ]),
        ("Lights", [
            (["Fn", "X"], "Turn the lights on or off"),
            (["Fn", "|"], "Cycle through the 20 effects"),
            (["Fn", "↑"], "Brightness up (5 levels)"),
            (["Fn", "↓"], "Brightness down"),
            (["Fn", "→"], "Change the color"),
            (["Fn", "←"], "Change the effect direction"),
            (["Fn", "="], "Faster"),
            (["Fn", "-"], "Slower"),
        ]),
        ("Gaming light modes", [
            (["Fn", "1"], "FPS mode"),
            (["Fn", "2"], "LOL mode"),
            (["Fn", "3"], "Office mode"),
            (["Fn", "~"], "Record your own light mode"),
        ]),
        ("Connection", [
            (["Fn", "Q"], "Bluetooth 1 (hold 3 s to pair)"),
            (["Fn", "W"], "Bluetooth 2 (hold 3 s to pair)"),
            (["Fn", "E"], "Bluetooth 3 (hold 3 s to pair)"),
            (["Fn", "R"], "2.4G receiver (hold 3 s to pair)"),
        ]),
        ("System", [
            (["Fn", "Space"], "Hold 3-5 s to factory reset"),
        ]),
    ]

    def build_shortcuts(self):
        w, v = self.page(tr("Shortcuts"),
                         tr("They work directly on the keyboard, without the app (per the AK832 Pro manual)."))
        for title, items in self.SHORTCUTS:
            rows = []
            for keys, desc in items:
                combo = QHBoxLayout()
                combo.setSpacing(4)
                for i, k in enumerate(keys):
                    if i:
                        combo.addWidget(T.text("+", "secondary"))
                    combo.addWidget(T.text(tr(k), "keycap"))
                rows.append(T.row(tr(desc), combo))
            v.addWidget(T.group(*rows, header=tr(title)))
        v.addStretch()
        return w


class Controller:
    """Owns the main window so it can be rebuilt (e.g. after changing the language)."""

    def __init__(self, start_hidden):
        self.win = MainWindow(self, start_hidden)

    def rebuild(self, page=0):
        old = self.win
        geo, visible = old.saveGeometry(), old.isVisible()
        old.shutdown()
        self.win = MainWindow(self, start_hidden=True)
        self.win.restoreGeometry(geo)
        self.win.nav.setCurrentRow(page)
        if visible:
            self.win.show()
        old.hide()
        old.deleteLater()


def main():
    if sys.platform == "win32":
        # Without this, Windows groups the window under python.exe and shows a generic icon.
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
    i18n.set_language(settings.value("language", "system"))
    apply_appearance(app, settings.value("appearance", "system"))

    controller = Controller(start_hidden="--tray" in sys.argv)
    busy = {"on": False}

    def system_changed(*_):
        if busy["on"] or settings.value("appearance", "system") != "system":
            return
        busy["on"] = True
        apply_appearance(app, "system")
        controller.win.set_color(controller.win.color, select_mode=False)
        controller.win.on_status(controller.win.state, controller.win.battery)
        busy["on"] = False

    app.styleHints().colorSchemeChanged.connect(system_changed)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
