"""USB HID relay power controller."""
import argparse
import time

from .base import PowerController, run_controller

try:
    import hid  # type: ignore
    HID_AVAILABLE = True
except ImportError:
    HID_AVAILABLE = False

# Common USB relay vendor/product IDs (CH340-based boards)
RELAY_VID = 0x16C0
RELAY_PID = 0x05DF


class UsbRelayController(PowerController):
    def __init__(self, relay_id: int = 1):
        self.relay_id = relay_id

    def _send(self, state: bool) -> None:
        if not HID_AVAILABLE:
            print("WARNING: hidapi not available; skipping power control", flush=True)
            return
        h = hid.device()
        h.open(RELAY_VID, RELAY_PID)
        cmd = 0xFF if state else 0xFD
        h.write([0x00, cmd, self.relay_id, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        h.close()

    def on(self) -> None:
        self._send(True)

    def off(self) -> None:
        self._send(False)

    def reset(self) -> None:
        self.off()
        time.sleep(0.5)
        self.on()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--relay-id", type=int, default=1)
    args, _ = parser.parse_known_args()
    run_controller(UsbRelayController(relay_id=args.relay_id))
