import argparse
from abc import ABC, abstractmethod


class PowerController(ABC):
    @abstractmethod
    def on(self) -> None: ...

    @abstractmethod
    def off(self) -> None: ...

    @abstractmethod
    def reset(self) -> None: ...


def run_controller(controller: PowerController) -> None:
    parser = argparse.ArgumentParser(description="Device power control")
    parser.add_argument(
        "--action", choices=["on", "off", "reset"], required=True, help="Power action"
    )
    args, _ = parser.parse_known_args()
    getattr(controller, args.action)()
