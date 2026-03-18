#!/usr/bin/env python3
"""
squelch-tail-display — pygame display client for squelch-tail-cli.

Reads state as newline-delimited JSON from stdin (written by the CLI plugin)
and writes command JSON lines to stdout.

Usage (launched automatically by the CLI plugin):
  python3 main.py --mode lcd   [--width 320] [--height 480] [--rotate 0]
  python3 main.py --mode eink  [--width 250] [--height 122]

Test mode (opens a normal window on macOS / any desktop):
  python3 main.py --mode lcd  --test
  python3 main.py --mode eink --test

Pipe in a state message for a one-shot preview:
  echo '{"type":"state","connected":true,"lfActive":true,"playing":true,
         "elapsed":5.2,"queueLen":1,"volume":80,"paused":false,
         "call":{"systemId":1,"systemLabel":"Metro Police",
                 "talkgroupId":100,"tgLabel":"Fire Dispatch",
                 "freq":460012500,"emergency":false,"encrypted":false,
                 "units":[{"unitId":1234,"tag":"Engine 5"}]}}' \
  | python3 main.py --mode lcd --test
"""

import argparse
import sys


def main() -> None:
    p = argparse.ArgumentParser(description='Squelch Tail pygame display')
    p.add_argument('--mode',       choices=['lcd', 'eink'], default='lcd',
                   help='Display mode (default: lcd)')
    p.add_argument('--width',      type=int, default=None,
                   help='Display width in pixels')
    p.add_argument('--height',     type=int, default=None,
                   help='Display height in pixels')
    p.add_argument('--rotate',     type=int, default=0, choices=[0, 90, 180, 270],
                   help='Screen rotation degrees (lcd only, default: 0)')
    p.add_argument('--fullscreen', action='store_true',
                   help='Fullscreen mode (lcd only)')
    p.add_argument('--no-touch',   action='store_true',
                   help='Disable touch/mouse input (lcd only)')
    p.add_argument('--test',       action='store_true',
                   help='Test mode: open a normal desktop window (skips Pi-specific SDL setup)')
    args = p.parse_args()

    if args.mode == 'lcd':
        from squelch_display.lcd import LcdApp
        app = LcdApp(
            width      = args.width  or 480,
            height     = args.height or 320,
            rotate     = args.rotate,
            fullscreen = args.fullscreen,
            touch      = not args.no_touch,
            test       = args.test,
        )
    else:
        from squelch_display.eink import EinkApp
        app = EinkApp(
            width  = args.width  or 250,
            height = args.height or 122,
            test   = args.test,
        )

    try:
        app.run()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
