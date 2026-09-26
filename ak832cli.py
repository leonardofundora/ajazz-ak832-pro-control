"""Command line:
    python ak832cli.py time
    python ak832cli.py lights static ff0000
    python ak832cli.py settings --sleep 2
    python ak832cli.py screen photo.gif
"""
import argparse
from datetime import datetime

from ak832 import protocol as P
from ak832 import screen
from ak832.device import Keyboard


def main():
    ap = argparse.ArgumentParser(prog="ak832", description="Control the AJAZZ AK832 Pro over USB.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("time", help="set the keyboard clock")
    t.add_argument("--at", help="YYYY-MM-DD HH:MM:SS (defaults to this computer's time)")

    l = sub.add_parser("lights", help="set the lighting effect")
    l.add_argument("effect", choices=[e.name.lower() for e in P.Effect])
    l.add_argument("color", nargs="?", default="ffffff", help="hex color, e.g. ff0000")
    l.add_argument("--brightness", type=int, default=5, help="0-5")
    l.add_argument("--speed", type=int, default=3, help="0-5")
    l.add_argument("--multicolor", action="store_true", help="use multicolor instead of the given color")
    l.add_argument("--direction", choices=[d.name.lower() for d in P.Direction], default="left")

    s = sub.add_parser("settings", help="save keyboard settings")
    s.add_argument("--sleep", type=int, choices=range(4), default=2,
                   help="turn lights off when idle: 0 never, 1 = 1 min, 2 = 5 min, 3 = 30 min")
    s.add_argument("--response", type=int, choices=range(1, 6), default=2, help="key response time 1-5")
    s.add_argument("--game-mode", action="store_true")

    sc = sub.add_parser("screen", help="upload an image or GIF to the screen")
    sc.add_argument("file")
    sc.add_argument("--scaling", choices=["fill", "fit", "stretch"], default="fill")

    args = ap.parse_args()
    with Keyboard(log=print) as kb:
        if args.cmd == "time":
            kb.set_time(datetime.strptime(args.at, "%Y-%m-%d %H:%M:%S") if args.at else datetime.now())
        elif args.cmd == "lights":
            c = args.color.lstrip("#")
            kb.set_lighting(P.Lighting(P.Effect[args.effect.upper()],
                                       (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)),
                                       not args.multicolor, args.brightness, args.speed,
                                       P.Direction[args.direction.upper()]))
        elif args.cmd == "settings":
            kb.set_settings(P.Settings(game_mode=args.game_mode, light_sleep=P.Sleep(args.sleep),
                                       key_response=args.response))
        elif args.cmd == "screen":
            frames, delays = screen.load_frames(args.file, args.scaling)
            kb.upload_animation([screen.to_rgb565(f) for f in frames], delays,
                                lambda i, n: print("\r  %d/%d" % (i, n), end="", flush=True))
            print()


if __name__ == "__main__":
    main()
