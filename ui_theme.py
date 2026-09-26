"""Tema inspirado en Liquid Glass (macOS 26 Tahoe): vidrio translúcido, barra lateral flotante,
controles en cápsula y esquinas concéntricas. Qt no tiene el material de vidrio real de Apple,
así que se imita con paneles translúcidos sobre un fondo de color suave."""

import os
import sys
import tempfile

from PySide6.QtCore import (
    Property, QByteArray, QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt, Signal,
)
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

IS_MAC = sys.platform == "darwin"

# Radios concéntricos: ventana > panel (22) > grupo (18) > control (cápsula).
R_PANEL, R_GROUP = 22, 18

LIGHT = dict(
    dark=False,
    base="#EDEFF4", blobs=[("#6EA8FF", 70), ("#B69CFF", 60), ("#6FE3D1", 45)],
    glass_top="rgba(255,255,255,0.78)", glass_bottom="rgba(255,255,255,0.58)", glass_edge="rgba(255,255,255,0.95)",
    glass_line="rgba(0,0,0,0.07)",
    side_top="rgba(255,255,255,0.62)", side_bottom="rgba(255,255,255,0.44)",
    text="#1D1D1F", secondary="#6E6E73", tertiary="#A1A1A6", separator="rgba(60,60,67,0.12)",
    fill="rgba(120,120,128,0.13)", fill_hover="rgba(120,120,128,0.22)",
    seg_on="#FFFFFF", knob="#FFFFFF", track_off="#DADADF",
    accent="#0088FF", accent_hover="#2E9BFF", accent_text="#FFFFFF",
    green="#34C759", screen="#000000",
)
DARK = dict(
    dark=True,
    base="#111114", blobs=[("#1F4FD8", 95), ("#6D28D9", 80), ("#0F9F8F", 55)],
    glass_top="rgba(255,255,255,0.10)", glass_bottom="rgba(255,255,255,0.05)", glass_edge="rgba(255,255,255,0.16)",
    glass_line="rgba(0,0,0,0.35)",
    side_top="rgba(58,58,64,0.62)", side_bottom="rgba(36,36,40,0.55)",
    text="#F5F5F7", secondary="#A1A1A6", tertiary="#6B6B70", separator="rgba(255,255,255,0.09)",
    fill="rgba(120,120,128,0.26)", fill_hover="rgba(120,120,128,0.36)",
    seg_on="rgba(255,255,255,0.24)", knob="#FFFFFF", track_off="#48484C",
    accent="#0A91FF", accent_hover="#3DA8FF", accent_text="#FFFFFF",
    green="#30D158", screen="#000000",
)

current = dict(LIGHT)  # los controles pintados a mano leen de aquí

# --------------------------------------------------------------------------- íconos (trazos tipo SF Symbols)

GLYPHS = {
    "clock": '<circle cx="12" cy="12" r="8.5" fill="none" stroke="#fff" stroke-width="2"/>'
             '<path d="M12 7.5V12l3 2" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"/>',
    "bulb": '<path d="M12 3.5a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1 2V17h5.2v-.7c0-.8.4-1.5 1-2A6 6 0 0 0 12 3.5z" '
            'fill="#fff"/><rect x="9.6" y="18.3" width="4.8" height="1.6" rx=".8" fill="#fff"/>'
            '<rect x="10.4" y="20.6" width="3.2" height="1.4" rx=".7" fill="#fff"/>',
    "photo": '<rect x="3.5" y="5" width="17" height="14" rx="2.5" fill="none" stroke="#fff" stroke-width="2"/>'
             '<path d="M5 17l4.5-5 3.5 3.5 2.5-2.5L19 17z" fill="#fff"/><circle cx="15.5" cy="9" r="1.6" fill="#fff"/>',
    "sliders": '<g stroke="#fff" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></g>'
               '<g fill="#fff"><circle cx="9" cy="7" r="2.6"/><circle cx="15" cy="12" r="2.6"/>'
               '<circle cx="8" cy="17" r="2.6"/></g>',
    "keyboard": '<rect x="2.5" y="6" width="19" height="12" rx="2.5" fill="none" stroke="#fff" stroke-width="2"/>'
                '<g fill="#fff"><rect x="5.5" y="9" width="2" height="2" rx=".5"/><rect x="9" y="9" width="2" '
                'height="2" rx=".5"/><rect x="12.5" y="9" width="2" height="2" rx=".5"/><rect x="16" y="9" '
                'width="2" height="2" rx=".5"/><rect x="7.5" y="13" width="9" height="2" rx="1"/></g>',
}
TILE_COLORS = {"clock": ("#FFB340", "#FF8A00"), "bulb": ("#FFD84D", "#FFB800"), "photo": ("#C57BFF", "#9A4DFF"),
               "sliders": ("#A5A5AD", "#77777F"), "keyboard": ("#8A8A92", "#56565E")}


def _svg_pixmap(svg, size, ratio=2.0):
    r = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    r.render(p)
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def tile_icon(name, size=24):
    """Ícono en un 'squircle' con degradado y brillo, como la barra lateral de Ajustes en Tahoe."""
    top, bottom = TILE_COLORS[name]
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><defs>'
           '<linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="%s"/>'
           '<stop offset="1" stop-color="%s"/></linearGradient></defs>'
           '<rect width="24" height="24" rx="7" fill="url(#g)"/>'
           '<rect x=".5" y=".5" width="23" height="23" rx="6.5" fill="none" stroke="#fff" stroke-opacity=".35"/>'
           '<g transform="translate(4 4) scale(.667)">%s</g></svg>' % (top, bottom, GLYPHS[name]))
    icon = QIcon()
    pm = _svg_pixmap(svg, size)
    for mode in (QIcon.Normal, QIcon.Selected, QIcon.Active):
        icon.addPixmap(pm, mode)
    return icon


_ASSET_DIR = os.path.join(tempfile.gettempdir(), "ajazz_control_ui")


def _chevron_file(color, name):
    os.makedirs(_ASSET_DIR, exist_ok=True)
    path = os.path.join(_ASSET_DIR, name)
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="14" viewBox="0 0 10 14">'
           '<path d="M2 5l3-3 3 3M2 9l3 3 3-3" fill="none" stroke="%s" stroke-width="1.6" '
           'stroke-linecap="round" stroke-linejoin="round"/></svg>' % color)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    return path.replace("\\", "/")


# --------------------------------------------------------------------------- hoja de estilos

def stylesheet(t):
    dark = t["dark"]
    chevron = _chevron_file(t["secondary"], "chevron_%s.svg" % ("dark" if dark else "light"))
    glass = (f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {t['glass_top']}, stop:1 {t['glass_bottom']})")
    side = (f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {t['side_top']}, stop:1 {t['side_bottom']})")
    return f"""
* {{ outline: 0; }}
QWidget {{ color: {t['text']}; font-size: 13px; }}
QScrollArea, QScrollArea > QWidget > QWidget, QWidget#content, QStackedWidget {{ background: transparent; }}
QToolTip {{ background: {t['base']}; color: {t['text']}; border: 1px solid {t['glass_line']}; padding: 5px 8px; border-radius: 8px; }}

QWidget#sidebar {{ background: {side}; border: 1px solid {t['glass_edge']}; border-radius: {R_PANEL}px; }}
QListWidget#nav {{ background: transparent; border: none; padding: 2px 8px; }}
QListWidget#nav::item {{ padding: 7px 8px; border-radius: 11px; margin: 1px 0; color: {t['text']}; }}
QListWidget#nav::item:hover:!selected {{ background: {t['fill']}; }}
QListWidget#nav::item:selected {{ background: {t['accent']}; color: {t['accent_text']}; }}
QLabel#appName {{ font-size: 15px; font-weight: 700; padding-left: 18px; }}
QLabel#sideStatus {{ background: {t['fill']}; border-radius: 13px; padding: 6px 12px; font-size: 12px; }}

QLabel {{ background: transparent; }}
QLabel#largeTitle {{ font-size: 30px; font-weight: 800; }}
QLabel#subtitle, QLabel#secondary {{ color: {t['secondary']}; }}
QLabel#subtitle {{ font-size: 14px; }}
QLabel#groupHeader {{ color: {t['secondary']}; font-size: 13px; font-weight: 700; padding-left: 16px; }}
QLabel#footnote {{ color: {t['secondary']}; font-size: 12px; padding-left: 16px; }}
QLabel#rowTitle {{ font-size: 13px; font-weight: 500; }}
QLabel#rowSub {{ color: {t['secondary']}; font-size: 11px; }}
QLabel#clock {{ font-size: 64px; font-weight: 250; }}
QLabel#value {{ color: {t['secondary']}; min-width: 18px; }}
QLabel#keycap {{ background: {glass}; border: 1px solid {t['glass_edge']}; border-bottom: 2px solid {t['glass_line']};
                 border-radius: 8px; padding: 3px 10px; font-size: 12px; font-weight: 700; }}
QLabel#preview {{ background: {t['screen']}; border-radius: 16px; border: 7px solid {'#2C2C30' if dark else '#1D1D1F'}; color: #8E8E93; }}

QFrame#group {{ background: {glass}; border: 1px solid {t['glass_edge']}; border-radius: {R_GROUP}px; }}
QFrame#separator {{ background: {t['separator']}; max-height: 1px; min-height: 1px; border: none; }}

QPushButton {{ background: {t['fill']}; border: 1px solid {t['glass_edge'] if not dark else 'rgba(255,255,255,0.08)'};
               border-radius: 15px; padding: 6px 16px; font-size: 13px; font-weight: 500; min-height: 18px; }}
QPushButton:hover {{ background: {t['fill_hover']}; }}
QPushButton:disabled {{ color: {t['tertiary']}; }}
QPushButton#primary {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {t['accent_hover']}, stop:1 {t['accent']});
               color: {t['accent_text']}; border: 1px solid rgba(255,255,255,0.35); border-radius: 19px;
               font-size: 14px; font-weight: 700; padding: 9px 24px; }}
QPushButton#primary:hover {{ background: {t['accent_hover']}; }}
QPushButton#primary:disabled {{ background: {t['fill']}; color: {t['tertiary']}; border-color: transparent; }}
QPushButton#chip {{ background: {t['fill']}; border: 1px solid transparent; border-radius: 17px; padding: 7px 10px; }}
QPushButton#chip:hover {{ background: {t['fill_hover']}; }}
QPushButton#chip:checked {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {t['accent_hover']}, stop:1 {t['accent']});
               color: {t['accent_text']}; font-weight: 700; border: 1px solid rgba(255,255,255,0.35); }}

QWidget#segbox {{ background: {t['fill']}; border-radius: 16px; }}
QPushButton#seg {{ background: transparent; border: 1px solid transparent; border-radius: 13px; padding: 4px 14px; margin: 2px; min-height: 18px; }}
QPushButton#seg:hover {{ background: transparent; }}
QPushButton#seg:checked {{ background: {t['seg_on']}; border: 1px solid {t['glass_edge']}; }}

QComboBox, QDateTimeEdit, QSpinBox {{ background: {t['fill']}; border: 1px solid transparent; border-radius: 15px;
               padding: 5px 28px 5px 14px; min-height: 18px; }}
QComboBox:hover, QDateTimeEdit:hover, QSpinBox:hover {{ background: {t['fill_hover']}; }}
QComboBox::drop-down, QDateTimeEdit::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow, QDateTimeEdit::down-arrow {{ image: url({chevron}); }}
QComboBox QAbstractItemView {{ background: {t['base']}; border: 1px solid {t['glass_line']}; border-radius: 12px;
               selection-background-color: {t['accent']}; selection-color: {t['accent_text']}; padding: 6px; }}
QSpinBox {{ padding-right: 14px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}

QSlider {{ min-height: 26px; }}
QSlider::groove:horizontal {{ height: 6px; background: {t['fill']}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {t['knob']}; width: 32px; margin: -8px 0; border-radius: 11px;
               border: 1px solid {'rgba(0,0,0,0.12)' if not dark else 'rgba(255,255,255,0.25)'}; }}

QProgressBar {{ background: {t['fill']}; border: none; border-radius: 4px; max-height: 8px; min-height: 8px; }}
QProgressBar::chunk {{ background: {t['accent']}; border-radius: 4px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {t['fill_hover']}; border-radius: 3px; min-height: 30px; margin: 0 2px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: transparent; }}

QMenu {{ background: {t['base']}; border: 1px solid {t['glass_line']}; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 6px 20px; border-radius: 8px; }}
QMenu::item:selected {{ background: {t['accent']}; color: {t['accent_text']}; }}
"""


# --------------------------------------------------------------------------- fondo y efectos

class Backdrop(QWidget):
    """Fondo de la ventana: color base con manchas de luz difusas para que el vidrio 'refracte' algo."""

    def paintEvent(self, _):
        t = current
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(t["base"]))
        w, h = self.width(), self.height()
        spots = [(0.12, 0.10, 0.55), (0.92, 0.85, 0.60), (0.70, 0.05, 0.40)]
        for (fx, fy, fr), (color, alpha) in zip(spots, t["blobs"]):
            c = QColor(color)
            g = QRadialGradient(QPointF(w * fx, h * fy), max(w, h) * fr)
            c.setAlpha(alpha)
            g.setColorAt(0, c)
            c.setAlpha(0)
            g.setColorAt(1, c)
            p.fillRect(self.rect(), g)
        p.end()


class ScrollEdge(QWidget):
    """Efecto de borde suave (scroll edge): el contenido se desvanece bajo el borde superior."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, _):
        c = QColor(current["base"])
        g = QLinearGradient(0, 0, 0, self.height())
        c.setAlpha(235)
        g.setColorAt(0, c)
        c.setAlpha(0)
        g.setColorAt(1, c)
        p = QPainter(self)
        p.fillRect(self.rect(), g)
        p.end()


def float_shadow(widget, blur=36, alpha=None):
    fx = QGraphicsDropShadowEffect(widget)
    fx.setBlurRadius(blur)
    fx.setOffset(0, 8)
    fx.setColor(QColor(0, 0, 0, alpha if alpha is not None else (110 if current["dark"] else 35)))
    widget.setGraphicsEffect(fx)
    return fx


# --------------------------------------------------------------------------- controles

class Toggle(QAbstractButton):
    """Interruptor al estilo macOS 26: pista en cápsula y perilla de vidrio alargada."""

    W, H = 46, 26

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutBack)
        self.toggled.connect(self._animate)

    def sizeHint(self):
        return QSize(self.W, self.H)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _get_pos(self):
        return self._pos

    def _set_pos(self, v):
        self._pos = v
        self.update()

    knob = Property(float, _get_pos, _set_pos)  # no llamarla "pos": QWidget ya la usa

    def paintEvent(self, _):
        t = current
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        k = max(0.0, min(1.0, self._pos))
        off, on = QColor(t["track_off"]), QColor(t["green"])
        track = QColor(int(off.red() + (on.red() - off.red()) * k), int(off.green() + (on.green() - off.green()) * k),
                       int(off.blue() + (on.blue() - off.blue()) * k))
        if not self.isEnabled():
            track.setAlphaF(0.45)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, self.W, self.H), self.H / 2, self.H / 2)
        kw, kh = 28, 22
        x = 2 + self._pos * (self.W - kw - 4)
        knob = QRectF(x, (self.H - kh) / 2, kw, kh)
        p.setBrush(QColor(0, 0, 0, 45))
        p.drawRoundedRect(knob.translated(0, 1), kh / 2, kh / 2)
        g = QLinearGradient(0, knob.top(), 0, knob.bottom())
        g.setColorAt(0, QColor(255, 255, 255))
        g.setColorAt(1, QColor(242, 242, 247))
        p.setBrush(g)
        if not self.isEnabled():
            p.setOpacity(0.8)
        p.drawRoundedRect(knob, kh / 2, kh / 2)
        p.end()


class Segmented(QWidget):
    """Control segmentado en cápsula. changed(data) al elegir."""

    changed = Signal(object)

    def __init__(self, items, current_data=None, parent=None):
        super().__init__(parent)
        self.setObjectName("segbox")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.group = QButtonGroup(self)
        self._data = {}
        for i, (text_, data) in enumerate(items):
            b = QPushButton(text_)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.group.addButton(b, i)
            self._data[i] = data
            lay.addWidget(b)
            if data == current_data or (current_data is None and i == 0):
                b.setChecked(True)
        self.group.idClicked.connect(lambda i: self.changed.emit(self._data[i]))

    def data(self):
        return self._data.get(self.group.checkedId())

    def set_data(self, data):
        for i, d in self._data.items():
            if d == data:
                self.group.button(i).setChecked(True)


# --------------------------------------------------------------------------- composición

def text(s, name=None, wrap=False):
    l = QLabel(s)
    if name:
        l.setObjectName(name)
    l.setWordWrap(wrap)
    return l


def separator():
    f = QFrame()
    f.setObjectName("separator")
    return f


def row(title, control=None, subtitle=None):
    """Fila de un grupo: título (y subtítulo) a la izquierda, control a la derecha."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(18, 11, 14, 11)
    h.setSpacing(12)
    col = QVBoxLayout()
    col.setSpacing(2)
    col.addWidget(text(title, "rowTitle", wrap=True))
    if subtitle:
        col.addWidget(text(subtitle, "rowSub", wrap=True))
    h.addLayout(col, 1)
    if control is not None:
        if isinstance(control, QWidget):
            h.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)
        else:
            h.addLayout(control)
    return w


def group(*rows, header=None, footer=None, padded=False):
    """Grupo de vidrio con esquinas grandes y filas separadas por líneas finas."""
    outer = QWidget()
    v = QVBoxLayout(outer)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(7)
    if header:
        v.addWidget(text(header, "groupHeader"))
    box = QFrame()
    box.setObjectName("group")
    inner = QVBoxLayout(box)
    if padded:
        inner.setContentsMargins(16, 16, 16, 16)
        inner.setSpacing(12)
    else:
        inner.setContentsMargins(0, 3, 0, 3)
        inner.setSpacing(0)
    for i, r in enumerate(rows):
        if i and not padded:
            wrap = QHBoxLayout()
            wrap.setContentsMargins(18, 0, 18, 0)
            wrap.addWidget(separator())
            inner.addLayout(wrap)
        if isinstance(r, QWidget):
            inner.addWidget(r)
        else:
            inner.addLayout(r)
    v.addWidget(box)
    if footer:
        v.addWidget(text(footer, "footnote", wrap=True))
    return outer
