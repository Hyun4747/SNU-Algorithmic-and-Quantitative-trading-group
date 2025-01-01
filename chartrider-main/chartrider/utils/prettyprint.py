from enum import Enum, auto
from typing import Any

import click

from chartrider.utils.htmlsnippets import HTMLElement


class PrettyPrintMode(Enum):
    terminal = auto()
    light_html = auto()  # for telegram
    full_html = auto()  # for plot


class PrettyPrint:
    def __init__(
        self, left_spacing: int = 30, right_spacing: int = 30, mode: PrettyPrintMode = PrettyPrintMode.terminal
    ):
        self.left_spacing = left_spacing
        self.right_spacing = right_spacing
        self.mode = mode
        self.__builder_string = ""

    @property
    def light_html(self) -> bool:
        return self.mode == PrettyPrintMode.light_html

    @property
    def full_html(self) -> bool:
        return self.mode == PrettyPrintMode.full_html

    def header(self, text: str, divider: str = "="):
        if self.light_html:
            ret = f"\n<b>{text}</b>\n"
            self.__builder_string += ret
            return
        if self.full_html:
            ret = HTMLElement.h1(text).render() if divider == "=" else HTMLElement.h2(text).render()
            self.__builder_string += ret
            return
        text = f" {text} "
        total_width = self.left_spacing + self.right_spacing
        ret = "\n" + text.center(total_width, divider) + "\n"
        ret = click.style(ret, bold=True)
        self.__builder_string += ret

    def subheader(self, text: str):
        if self.light_html:
            ret = f"\n<u>{text}</u>\n"
            self.__builder_string += ret
            return
        if self.full_html:
            ret = HTMLElement.h3(text).render()
            self.__builder_string += ret
            return
        text = click.style(text, underline=True)
        ret = f"[ {text} ]\n"
        ret = click.style(ret, bold=True, underline=True)
        self.__builder_string += ret

    def key_value(
        self,
        key: str,
        value: Any,
        decimal_places: int | None = None,
        colorize: bool = False,
        force_color: str | None = None,
    ):
        if decimal_places is not None and isinstance(value, float):
            value_str = f"{value:.{decimal_places}f}"
        else:
            value_str = str(value)

        if self.light_html:
            ret = f"<code>{key}: {value_str}</code>\n"
            self.__builder_string += ret
            return
        if self.full_html:
            color = (force_color or ("green" if value > 0 else "red")) if colorize else "black"
            ret = HTMLElement(
                "code",
                children=[
                    HTMLElement("strong", children=key),
                    HTMLElement("span", children=value_str, style=dict(color=color)),
                ],
                justify_space_between=True,
                margin_horizontal=0.5,
            ).render()
            self.__builder_string += ret
            return

        right_spacing = self.right_spacing

        if colorize or force_color:
            try:
                plain_value_str = value_str
                value_str = click.style(value_str, fg=force_color or ("green" if value > 0 else "red"))
                right_spacing += len(value_str) - len(plain_value_str)
            except TypeError:
                pass

        ret = f"{key:<{self.left_spacing}}{value_str:>{right_spacing}}\n"
        self.__builder_string += ret

    def newline(self):
        self.__builder_string += "\n"

    @property
    def result(self):
        return self.__builder_string

    def print(self):
        click.echo(self.__builder_string)


if __name__ == "__main__":
    pp = PrettyPrint(mode=PrettyPrintMode.full_html)
    pp.header("Hello World")
    pp.key_value("key", "value")
    pp.key_value("key", "value")
    pp.key_value("key", "value")
    pp.subheader("Subheader")
    pp.key_value("key", "value")
    pp.key_value("key", "value", colorize=True)
    pp.key_value("key", "value", force_color="red")
    print(pp.result.replace(".", "\\."))
