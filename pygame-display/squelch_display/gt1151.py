"""
GT1151 capacitive touch controller driver for Waveshare 2.13" Touch e-Paper HAT.

The GT1151 communicates over I2C (address 0x14 or 0x5D).
Touch coordinates are polled at ~20 ms intervals in a background thread.

Touch point record at 0x8150 (8 bytes, no track-ID prefix):
  [0] GT X low byte   (GT X axis, 0-122 = display Y axis, bottom→top)
  [1] GT X high byte
  [2] GT Y low byte   (GT Y axis, 0-250 = display X axis, left→right)
  [3] GT Y high byte
  [4] size low byte
  [5] size high byte
  [6] reserved
  [7] reserved

The GT1151 is configured in portrait mode (X_MAX=122, Y_MAX=250), so its
axes are swapped and the Y axis is inverted relative to the landscape display:
  display_x = gt_y          (GT Y 0-250 → display X 0-250)
  display_y = 121 - gt_x    (GT X 0=bottom, 122=top → display Y 0=top, 121=bottom)

Usage:
    reader = GT1151Reader(i2c_bus=1, on_touch=callback)
    reader.start()   # launches background thread
    reader.stop()    # call on cleanup
"""

import sys
import threading
import time


GT1151_ADDR    = 0x14
GT_REG_PID     = 0x8140   # 4-byte product ID
GT_REG_STATUS  = 0x814E   # buffer-ready flag + touch count
GT_REG_DATA    = 0x8150   # touch point records (8 bytes each, up to 5 points)
_POLL_INTERVAL = 0.02     # 50 Hz polling


def _read(bus, reg: int, length: int) -> bytes:
    """Read `length` bytes from a 16-bit register address."""
    from smbus2 import i2c_msg
    wr = i2c_msg.write(GT1151_ADDR, [(reg >> 8) & 0xFF, reg & 0xFF])
    rd = i2c_msg.read(GT1151_ADDR, length)
    bus.i2c_rdwr(wr, rd)
    return bytes(rd)


def _write(bus, reg: int, data: list) -> None:
    """Write bytes to a 16-bit register address."""
    from smbus2 import i2c_msg
    wr = i2c_msg.write(GT1151_ADDR, [(reg >> 8) & 0xFF, reg & 0xFF] + data)
    bus.i2c_rdwr(wr)


class GT1151Reader:
    """
    Background thread that polls the GT1151 and calls on_touch(x, y) on each press.

    Delivers display-space coordinates (landscape, origin top-left):
      x: 0-250 (left→right), y: 0-122 (top→bottom)
    """

    def __init__(self, on_touch, i2c_bus: int = 1):
        self._on_touch  = on_touch
        self._i2c_bus   = i2c_bus
        self._thread    = None
        self._stop_flag = threading.Event()

    def start(self) -> bool:
        """Start the polling thread. Returns False if hardware not available."""
        try:
            from smbus2 import SMBus
        except ImportError:
            print('[touch] smbus2 not available — touch disabled', file=sys.stderr)
            return False

        try:
            bus = SMBus(self._i2c_bus)
            pid = _read(bus, GT_REG_PID, 4)
            print(f'[touch] GT1151 found on I2C bus {self._i2c_bus}, '
                  f'PID={pid.decode("ascii", errors="replace")}', file=sys.stderr)
        except Exception as exc:
            print(f'[touch] GT1151 not found on I2C bus {self._i2c_bus}: {exc}',
                  file=sys.stderr)
            try:
                bus.close()
            except Exception:
                pass
            return False

        self._stop_flag.clear()
        self._thread = threading.Thread(
            target=self._poll_loop, args=(bus,), daemon=True, name='gt1151-poll')
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def _poll_loop(self, bus) -> None:
        prev_touching = False
        try:
            while not self._stop_flag.is_set():
                try:
                    status = _read(bus, GT_REG_STATUS, 1)[0]
                    buf_ready = bool(status & 0x80)
                    n_points  = status & 0x0F

                    if buf_ready and n_points > 0:
                        data = _read(bus, GT_REG_DATA, n_points * 8)
                        # GT1151 portrait layout: [gt_x_lo, gt_x_hi, gt_y_lo, gt_y_hi, ...]
                        # GT X (0-122) = display Y;  GT Y (0-250) = display X
                        gt_x = data[0] | (data[1] << 8)
                        gt_y = data[2] | (data[3] << 8)
                        display_x = gt_y
                        display_y = 121 - gt_x
                        if not prev_touching:
                            self._on_touch(display_x, display_y)
                        prev_touching = True
                    else:
                        prev_touching = False

                    # Always clear buffer-ready flag after reading
                    if buf_ready:
                        _write(bus, GT_REG_STATUS, [0])

                except Exception as exc:
                    print(f'[touch] poll error: {exc}', file=sys.stderr)
                    time.sleep(0.5)   # back off on error

                time.sleep(_POLL_INTERVAL)
        finally:
            try:
                bus.close()
            except Exception:
                pass
