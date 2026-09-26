"""Acceso HID al teclado (Windows, macOS y Linux vía hidapi)."""

import time
from datetime import datetime

import hid

from . import protocol as P

KNOWN_IDS = [
    (0x05AC, 0x024F),  # AJAZZ AK832 Pro (sí, usa el VID de Apple)
    (0x0C45, 0x8009),  # AK820 Pro / AK980 Pro, misma familia de protocolo
    (0x0C45, 0x800A),
]
CONTROL_USAGE_PAGE = 0xFF13  # interfaz 3: feature reports de 65 bytes
BULK_USAGE_PAGE = 0xFF68     # interfaz 2: output reports de 4097 bytes

CMD_DELAY = 0.010  # el driver oficial espera 10 ms


class KeyboardError(Exception):
    pass


def _find_paths():
    control = bulk = None
    bluetooth = False
    for vid, pid in KNOWN_IDS:
        for d in hid.enumerate(vid, pid):
            path = d["path"]
            # Por Bluetooth el teclado aparece con el mismo VID/PID pero sin las
            # interfaces de configuración.
            bluetooth = True
            up, iface = d.get("usage_page", 0), d.get("interface_number", -1)
            if control is None and (up == CONTROL_USAGE_PAGE or (up == 0 and iface == 3)):
                control = path
            elif bulk is None and (up == BULK_USAGE_PAGE or (up == 0 and iface == 2)):
                bulk = path
        if control:
            return control, bulk, bluetooth
    return control, bulk, bluetooth


def is_connected() -> bool:
    return _find_paths()[0] is not None


def _is_bluetooth(d) -> bool:
    path = d["path"].decode(errors="ignore") if isinstance(d["path"], bytes) else str(d["path"])
    # hidapi >= 0.14 informa bus_type (2 = Bluetooth); en Windows la ruta lleva el UUID del servicio HID-over-GATT.
    return d.get("bus_type") == 2 or "00001812" in path.lower()


def connection_state():
    """Devuelve ("cable" | "bluetooth" | None, dirección BLE o None)."""
    if is_connected():
        return "cable", None
    import re
    for vid, pid in KNOWN_IDS:
        for d in hid.enumerate(vid, pid):
            if _is_bluetooth(d):
                path = d["path"].decode(errors="ignore") if isinstance(d["path"], bytes) else str(d["path"])
                m = re.search(r"rev&[0-9a-f]{4}_([0-9a-f]{12})", path.lower())
                return "bluetooth", (m.group(1) if m else None)
    return None, None


class Keyboard:
    """Uso:  with Keyboard() as kb: kb.set_time(datetime.now())"""

    def __init__(self, log=None):
        self.log = log or (lambda s: None)
        self.ctl = None
        self.bulk = None
        self._bulk_path = None

    # -- conexión --
    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *a):
        self.close()

    def open(self):
        control, bulk, bluetooth = _find_paths()
        if control is None:
            if bluetooth:
                raise KeyboardError(
                    "El teclado está conectado por Bluetooth o 2.4G. Conéctalo con el cable "
                    "USB (modo cable); de forma inalámbrica no se puede configurar.")
            raise KeyboardError(
                "No encuentro el teclado. Conéctalo con el cable USB y cierra el driver "
                "oficial de AJAZZ si está abierto.")
        self.ctl = hid.device()
        try:
            self.ctl.open_path(control)
        except OSError as e:
            raise KeyboardError(
                "No se pudo abrir el teclado (%s). En Mac: Ajustes del Sistema > Privacidad "
                "y seguridad > Monitorización de entrada, y permite esta app." % e)
        self._bulk_path = bulk
        self.log("Teclado conectado.")

    def close(self):
        for d in (self.ctl, self.bulk):
            if d is not None:
                try:
                    d.close()
                except Exception:
                    pass
        self.ctl = self.bulk = None

    # -- transporte --
    def _send(self, packet: bytes, ack: bool = True):
        assert len(packet) == P.PACKET_LEN
        report = b"\x00" + packet
        for _ in range(3):
            time.sleep(CMD_DELAY)
            if self.ctl.send_feature_report(report) < 0:
                raise KeyboardError("El teclado rechazó el comando 0x%02X." % packet[1])
            if not ack:
                return
            time.sleep(CMD_DELAY)
            try:
                resp = bytes(self.ctl.get_feature_report(0, 65))
            except (OSError, ValueError):
                return
            # Windows devuelve el Report ID delante; macOS/Linux a veces no.
            status = resp[4] if len(resp) == 65 else (resp[3] if len(resp) > 3 else 0)
            if status != 0xFF:
                return
            self.log("  el teclado pidió reintento…")
        raise KeyboardError("El teclado no respondió al comando 0x%02X." % packet[1])

    def _open_bulk(self):
        if self.bulk is None:
            if not self._bulk_path:
                raise KeyboardError("No se encontró la interfaz de la pantalla del teclado.")
            self.bulk = hid.device()
            self.bulk.open_path(self._bulk_path)
        return self.bulk

    # -- funciones --
    def set_time(self, t: datetime = None):
        t = t or datetime.now()
        self._send(P.start())
        self._send(P.time_preamble())
        self._send(P.time_data(t))
        self._send(P.save())
        self.log("Hora puesta: " + t.strftime("%d/%m/%Y %H:%M:%S"))

    def set_lighting(self, l: P.Lighting):
        self._send(P.start())
        self._send(P.light_preamble())
        self._send(P.light_data(l), ack=False)
        self._send(P.save())
        self._send(P.finish())
        self.log("Luces: %s" % P.EFFECT_NAMES.get(l.effect, l.effect))

    def set_settings(self, s: P.Settings):
        self._send(P.start())
        self._send(P.settings_preamble())
        self._send(P.settings_data(s))
        self._send(P.save())
        self.log("Ajustes guardados.")

    def upload_animation(self, frames_rgb565, delays_ms, progress=None):
        blob = P.animation_blob(frames_rgb565, delays_ms)
        chunks = P.split_chunks(blob)
        bulk = self._open_bulk()
        self._send(P.start())
        self._send(P.image_preamble(len(chunks)))
        for i, chunk in enumerate(chunks):
            if bulk.write(b"\x00" + chunk) < 0:
                raise KeyboardError("Falló el envío de la imagen (bloque %d)." % i)
            try:
                bulk.read(65, 200)  # acuse del teclado; el driver también lo lee
            except OSError:
                pass
            if progress:
                progress(i + 1, len(chunks))
        self._send(P.save())
        self.log("Pantalla actualizada (%d cuadros)." % min(len(frames_rgb565), P.MAX_FRAMES))
