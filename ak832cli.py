"""Línea de comandos:  python ak832cli.py hora | luces static ff0000 | ajustes --sleep 2 | pantalla foto.gif"""
import argparse
from datetime import datetime

from ak832 import protocol as P
from ak832.device import Keyboard
from ak832 import screen


def main():
    ap = argparse.ArgumentParser(prog="ak832")
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hora")
    h.add_argument("--fecha", help="AAAA-MM-DD HH:MM:SS (por defecto la hora del equipo)")
    l = sub.add_parser("luces")
    l.add_argument("efecto", choices=[e.name.lower() for e in P.Effect])
    l.add_argument("color", nargs="?", default="ffffff")
    l.add_argument("--brillo", type=int, default=5)
    l.add_argument("--velocidad", type=int, default=3)
    l.add_argument("--aleatorio", action="store_true", help="colores aleatorios en vez del color dado")
    l.add_argument("--direccion", choices=[d.name.lower() for d in P.Direction], default="left")
    a = sub.add_parser("ajustes")
    a.add_argument("--sleep", type=int, choices=range(4), default=2, help="0 nunca, 1=1min, 2=5min, 3=30min")
    a.add_argument("--respuesta", type=int, choices=range(1, 6), default=2)
    a.add_argument("--modo-juego", action="store_true")
    s = sub.add_parser("pantalla")
    s.add_argument("archivo")
    s.add_argument("--ajuste", choices=["fill", "fit", "stretch"], default="fill")
    args = ap.parse_args()

    with Keyboard(log=print) as kb:
        if args.cmd == "hora":
            t = datetime.strptime(args.fecha, "%Y-%m-%d %H:%M:%S") if args.fecha else datetime.now()
            kb.set_time(t)
        elif args.cmd == "luces":
            c = args.color.lstrip("#")
            kb.set_lighting(P.Lighting(P.Effect[args.efecto.upper()],
                                       (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)),
                                       not args.aleatorio, args.brillo, args.velocidad,
                                       P.Direction[args.direccion.upper()]))
        elif args.cmd == "ajustes":
            kb.set_settings(P.Settings(game_mode=args.modo_juego, light_sleep=P.Sleep(args.sleep),
                                       key_response=args.respuesta))
        elif args.cmd == "pantalla":
            frames, delays = screen.load_frames(args.archivo, args.ajuste)
            kb.upload_animation([screen.to_rgb565(f) for f in frames], delays,
                                lambda i, n: print("\r  %d/%d" % (i, n), end="", flush=True))
            print()


if __name__ == "__main__":
    main()
