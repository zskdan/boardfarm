"""No-op power controller for testing."""
import sys

from .base import PowerController, run_controller


class DummyController(PowerController):
    def on(self) -> None:
        print("POWER ON (dummy)", flush=True)

    def off(self) -> None:
        print("POWER OFF (dummy)", flush=True)

    def reset(self) -> None:
        print("POWER RESET (dummy): off then on", flush=True)


if __name__ == "__main__":
    run_controller(DummyController())
