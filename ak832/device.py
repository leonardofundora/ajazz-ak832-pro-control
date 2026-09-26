"""HID access to the keyboard (Windows, macOS and Linux via hidapi)."""

import time
from datetime import datetime

import hid

from . import protocol as P
from .i18n import tr

KNOWN_IDS = [
    (0x05AC, 0x024F),  # AJAZZ AK832 Pro (yes, it uses Apple's vendor ID)
    (0x0C45, 0x8009),  # AK820 Pro / AK980 Pro, same protocol family
    (0x0C45, 0x800A),
]
CONTROL_USAGE_PAGE = 0xFF13  # interface 3: 65-byte feature reports
BULK_USAGE_PAGE = 0xFF68     # interface 2: 4097-byte output reports

CMD_DELAY = 0.010  # the official driver waits 10 ms


class KeyboardError(Exception):
    pass


def _find_paths():
    control = bulk = None
    bluetooth = False
    for vid, pid in KNOWN_IDS:
        for d in hid.enumerate(vid, pid):
            path = d["path"]
            # Over Bluetooth the keyboard shows up with the same VID/PID but
            # without the configuration interfaces.
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
    # hidapi >= 0.14 reports bus_type (2 = Bluetooth); on Windows the path contains the HID-over-GATT service UUID.
    return d.get("bus_type") == 2 or "00001812" in path.lower()


def connection_state():
    """Returns ("cable" | "bluetooth" | None, BLE address or None)."""
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
    """Usage:  with Keyboard() as kb: kb.set_time(datetime.now())"""

    def __init__(self, log=None):
        self.log = log or (lambda s: None)
        self.ctl = None
        self.bulk = None
        self._bulk_path = None

    # -- connection --
    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *a):
        self.close()

    def open(self):
        control, bulk, bluetooth = _find_paths()
        if control is None:
            if bluetooth:
                raise KeyboardError(tr(
                    "The keyboard is connected via Bluetooth or 2.4G. Connect it with the USB cable "
                    "(wired mode); it can't be configured wirelessly."))
            raise KeyboardError(tr(
                "Keyboard not found. Connect it with the USB cable and close the official AJAZZ "
                "driver if it's open."))
        self.ctl = hid.device()
        try:
            self.ctl.open_path(control)
        except OSError as e:
            raise KeyboardError(tr(
                "Couldn't open the keyboard (%s). On Mac: System Settings > Privacy & Security > "
                "Input Monitoring, and allow this app.", e))
        self._bulk_path = bulk
        self.log(tr("Keyboard connected."))

    def close(self):
        for d in (self.ctl, self.bulk):
            if d is not None:
                try:
                    d.close()
                except Exception:
                    pass
        self.ctl = self.bulk = None

    # -- transport --
    def _send(self, packet: bytes, ack: bool = True):
        assert len(packet) == P.PACKET_LEN
        report = b"\x00" + packet
        for _ in range(3):
            time.sleep(CMD_DELAY)
            if self.ctl.send_feature_report(report) < 0:
                raise KeyboardError(tr("The keyboard rejected command 0x%02X.", packet[1]))
            if not ack:
                return
            time.sleep(CMD_DELAY)
            try:
                resp = bytes(self.ctl.get_feature_report(0, 65))
            except (OSError, ValueError):
                return
            # Windows returns the report ID first; macOS/Linux sometimes don't.
            status = resp[4] if len(resp) == 65 else (resp[3] if len(resp) > 3 else 0)
            if status != 0xFF:
                return
            self.log(tr("  the keyboard asked to retry…"))
        raise KeyboardError(tr("The keyboard didn't answer command 0x%02X.", packet[1]))

    def _open_bulk(self):
        if self.bulk is None:
            if not self._bulk_path:
                raise KeyboardError(tr("The keyboard's screen interface wasn't found."))
            self.bulk = hid.device()
            self.bulk.open_path(self._bulk_path)
        return self.bulk

    # -- features --
    def set_time(self, t: datetime = None):
        t = t or datetime.now()
        self._send(P.start())
        self._send(P.time_preamble())
        self._send(P.time_data(t))
        self._send(P.save())
        self.log(tr("Time set: %s", t.strftime("%Y-%m-%d %H:%M:%S")))

    def set_lighting(self, l: P.Lighting):
        self._send(P.start())
        self._send(P.light_preamble())
        self._send(P.light_data(l), ack=False)
        self._send(P.save())
        self._send(P.finish())
        self.log(tr("Lights: %s", P.effect_name(l.effect)))

    def set_settings(self, s: P.Settings):
        self._send(P.start())
        self._send(P.settings_preamble())
        self._send(P.settings_data(s))
        self._send(P.save())
        self.log(tr("Settings saved."))

    def upload_animation(self, frames_rgb565, delays_ms, progress=None):
        blob = P.animation_blob(frames_rgb565, delays_ms)
        chunks = P.split_chunks(blob)
        bulk = self._open_bulk()
        self._send(P.start())
        self._send(P.image_preamble(len(chunks)))
        for i, chunk in enumerate(chunks):
            if bulk.write(b"\x00" + chunk) < 0:
                raise KeyboardError(tr("Sending the image failed (chunk %d).", i))
            try:
                bulk.read(65, 200)  # keyboard acknowledgement; the driver reads it too
            except OSError:
                pass
            if progress:
                progress(i + 1, len(chunks))
        self._send(P.save())
        self.log(tr("Screen updated (%d frames).", min(len(frames_rgb565), P.MAX_FRAMES)))
