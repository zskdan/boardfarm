"""Raspberry Pi GPIO power controller."""
import argparse
import time

from .base import PowerController, run_controller

try:
    import RPi.GPIO as GPIO  # type: ignore
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False


class GpioController(PowerController):
    def __init__(self, gpio_pin: int = 17, active_low: bool = False):
        self.pin = gpio_pin
        self.active_low = active_low
        if GPIO_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.OUT)

    def _set(self, on: bool) -> None:
        if not GPIO_AVAILABLE:
            print("WARNING: RPi.GPIO not available; skipping power control", flush=True)
            return
        level = GPIO.LOW if (on ^ self.active_low) else GPIO.HIGH
        GPIO.output(self.pin, level)

    def on(self) -> None:
        self._set(True)

    def off(self) -> None:
        self._set(False)

    def reset(self) -> None:
        self.off()
        time.sleep(0.5)
        self.on()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--gpio-pin", type=int, default=17)
    parser.add_argument("--active-low", action="store_true")
    args, _ = parser.parse_known_args()
    run_controller(GpioController(gpio_pin=args.gpio_pin, active_low=args.active_low))
