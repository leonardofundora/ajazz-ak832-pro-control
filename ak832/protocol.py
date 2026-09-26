"""HID packets for the AJAZZ AK832 Pro.

Everything was extracted from the official Windows driver (DeviceDriver.exe V1.0)
and verified on a real keyboard:

  time     0x437B20   18 -> 28 -> data -> 02
  lights   0x42D290   18 -> 13 -> data -> 02 -> F0
  settings 0x436B20   18 -> 17 -> data -> 02
  screen   0x4237A0   18 -> 72 -> N chunks of 4096 B (image interface) -> 02

Control packets are 64 bytes and travel as HID feature reports prefixed with
report ID 0x00 (65 bytes total) on interface 3 (usage page 0xFF13).
Images travel as output reports [0x00] + 4096 bytes on interface 2
(usage page 0xFF68).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum

from .i18n import tr

PACKET_LEN = 64
TAIL = (0xAA, 0x55)

CMD_SAVE = 0x02
CMD_LIGHT = 0x13
CMD_SETTINGS = 0x17
CMD_START = 0x18
CMD_TIME = 0x28
CMD_IMAGE = 0x72
CMD_FINISH = 0xF0


def command(cmd: int, b2: int = 0, b8: int = 0, b9: int = 0) -> bytes:
    p = bytearray(PACKET_LEN)
    p[0] = 0x04
    p[1] = cmd
    p[2] = b2
    p[8] = b8
    p[9] = b9
    return bytes(p)


def start() -> bytes:
    return command(CMD_START)


def save() -> bytes:
    return command(CMD_SAVE)


def finish() -> bytes:
    return command(CMD_FINISH)


# --- Time -------------------------------------------------------------------

def time_preamble() -> bytes:
    return command(CMD_TIME, b8=0x01)


def time_data(t: datetime, slot: int = 1) -> bytes:
    p = bytearray(PACKET_LEN)
    p[0] = 0x00
    p[1] = slot
    p[2] = 0x5A
    p[3] = t.year % 2000
    p[4] = t.month
    p[5] = t.day
    p[6] = t.hour
    p[7] = t.minute
    p[8] = t.second
    p[62], p[63] = TAIL
    return bytes(p)


# --- Lights -----------------------------------------------------------------

class Effect(IntEnum):
    OFF = 0x00
    STATIC = 0x01
    SINGLE_ON = 0x02
    SINGLE_OFF = 0x03
    GLITTERING = 0x04
    FALLING = 0x05
    COLOURFUL = 0x06
    BREATH = 0x07
    SPECTRUM = 0x08
    OUTWARD = 0x09
    SCROLLING = 0x0A
    ROLLING = 0x0B
    ROTATING = 0x0C
    EXPLODE = 0x0D
    LAUNCH = 0x0E
    RIPPLES = 0x0F
    FLOWING = 0x10
    PULSATING = 0x11
    TILT = 0x12
    SHUTTLE = 0x13


_EFFECT_NAMES = {
    Effect.STATIC: "Static",
    Effect.SINGLE_ON: "Single on",
    Effect.SINGLE_OFF: "Single off",
    Effect.GLITTERING: "Glittering",
    Effect.FALLING: "Falling",
    Effect.COLOURFUL: "Colourful",
    Effect.BREATH: "Breath",
    Effect.SPECTRUM: "Spectrum",
    Effect.OUTWARD: "Outward",
    Effect.SCROLLING: "Scrolling",
    Effect.ROLLING: "Rolling",
    Effect.ROTATING: "Rotating",
    Effect.EXPLODE: "Explode",
    Effect.LAUNCH: "Launch",
    Effect.RIPPLES: "Ripples",
    Effect.FLOWING: "Flowing",
    Effect.PULSATING: "Pulsating",
    Effect.TILT: "Tilt",
    Effect.SHUTTLE: "Shuttle",
    Effect.OFF: "Off",
}


def effect_name(e) -> str:
    return tr(_EFFECT_NAMES.get(e, str(e)))


class Direction(IntEnum):
    LEFT = 0
    DOWN = 1
    UP = 2
    RIGHT = 3


EFFECT_DIRECTIONS = {
    Effect.SCROLLING: (Direction.UP, Direction.DOWN),
    Effect.ROLLING: (Direction.LEFT, Direction.RIGHT),
    Effect.FLOWING: (Direction.LEFT, Direction.RIGHT),
    Effect.TILT: (Direction.LEFT, Direction.RIGHT),
}

MAX_BRIGHTNESS = 5
MAX_SPEED = 5


@dataclass
class Lighting:
    effect: Effect = Effect.STATIC
    color: tuple = (255, 255, 255)
    custom_color: bool = True  # byte 8: 0 = chosen color, 1 = multicolor (verified on the keyboard)
    brightness: int = 5
    speed: int = 3
    direction: Direction = Direction.LEFT


def light_preamble() -> bytes:
    return command(CMD_LIGHT, b8=0x01)


def light_data(l: Lighting) -> bytes:
    p = bytearray(PACKET_LEN)
    p[0] = int(l.effect)
    p[1], p[2], p[3] = (max(0, min(255, int(c))) for c in l.color)
    p[8] = 0 if l.custom_color else 1
    p[9] = max(0, min(MAX_BRIGHTNESS, l.brightness))
    p[10] = max(0, min(MAX_SPEED, l.speed))
    p[11] = int(l.direction)
    p[14], p[15] = TAIL
    return bytes(p)


# --- Settings ---------------------------------------------------------------

class Sleep(IntEnum):
    NEVER = 0
    MIN_1 = 1
    MIN_5 = 2
    MIN_30 = 3


_SLEEP_NAMES = {
    Sleep.NEVER: "Never",
    Sleep.MIN_1: "1 minute",
    Sleep.MIN_5: "5 minutes",
    Sleep.MIN_30: "30 minutes",
}


def sleep_name(s) -> str:
    return tr(_SLEEP_NAMES[s])


@dataclass
class Settings:
    game_mode: bool = False
    block_alt_tab: bool = False
    block_alt_f4: bool = False
    block_win: bool = False
    light_sleep: Sleep = Sleep.MIN_5
    key_response: int = 2  # 1..5, the driver defaults to 2


def settings_preamble(profile: int = 1) -> bytes:
    return command(CMD_SETTINGS, b2=profile, b8=0x01)


def settings_data(s: Settings) -> bytes:
    p = bytearray(PACKET_LEN)
    if s.game_mode:
        p[1] = 1
        p[2] = 1 if s.block_alt_tab else 0
        p[3] = 1 if s.block_alt_f4 else 0
        p[4] = 1 if s.block_win else 0
    p[6] = int(s.light_sleep)
    p[8] = max(1, min(5, s.key_response))
    p[62], p[63] = TAIL
    return bytes(p)


# --- Screen -----------------------------------------------------------------

SCREEN_W = 160
SCREEN_H = 96
FRAME_BYTES = SCREEN_W * SCREEN_H * 2  # RGB565 = 0x7800
HEADER_BYTES = 0x100
CHUNK_BYTES = 0x1000
MAX_FRAMES = 255
MIN_DELAY_MS = 30
MAX_DELAY_MS = 500


def image_preamble(chunks: int, slot: int = 1) -> bytes:
    return command(CMD_IMAGE, b2=slot, b8=chunks & 0xFF, b9=(chunks >> 8) & 0xFF)


def animation_blob(frames_rgb565: list, delays_ms: list) -> bytes:
    """256-byte header + frames, padded with 0xFF to a multiple of 4096."""
    n = min(len(frames_rgb565), MAX_FRAMES)
    header = bytearray(b"\xff" * HEADER_BYTES)
    header[0] = n
    for i in range(n):
        header[1 + i] = max(1, min(255, int(delays_ms[i]) // 2))
    body = b"".join(frames_rgb565[:n])
    blob = bytes(header) + body
    pad = (-len(blob)) % CHUNK_BYTES
    return blob + b"\xff" * pad


def split_chunks(blob: bytes) -> list:
    return [blob[i:i + CHUNK_BYTES] for i in range(0, len(blob), CHUNK_BYTES)]
