from __future__ import annotations


class HTMLElement:
    def __init__(
        self,
        tag: str,
        children: HTMLElement | str | list[HTMLElement | str] = [],
        href: str | None = None,
        style: dict[str, str] | None = None,
        margin_bottom: float | None = None,
        margin_top: float | None = None,
        margin_horizontal: float | None = None,
        margin_vertical: float | None = None,
        padding: float | None = None,
        background_color: str | None = None,
        border_bottom: BorderStyle | None = None,
        justify_space_between: bool = False,
    ):
        self.tag = tag
        self.href = href
        self.style = style or {}
        if margin_bottom:
            self.style["margin-bottom"] = f"{margin_bottom}rem"
        if margin_top:
            self.style["margin-top"] = f"{margin_top}rem"
        if margin_horizontal is not None and margin_vertical is not None:
            self.style["margin"] = f"{margin_vertical}rem {margin_horizontal}rem"
        elif margin_horizontal:
            self.style["margin"] = f"0 {margin_horizontal}rem"
        elif margin_vertical:
            self.style["margin"] = f"{margin_vertical}rem 0"
        if padding:
            self.style["padding"] = f"{padding}rem"
        if background_color:
            self.style["background-color"] = background_color
        if border_bottom:
            self.style["border-bottom"] = border_bottom.render()
        if justify_space_between:
            self.style["display"] = "flex"
            self.style["justify-content"] = "space-between"

        # If 'children' is a single HTMLElement or str, wrap it in a list
        if isinstance(children, (HTMLElement, str)):
            self.children = [children]
        else:
            self.children = children

    def add_child(self, child: HTMLElement | str):
        self.children.append(child)

    def __render_style(self) -> str:
        if not self.style:
            return ""
        return 'style="' + "; ".join([f"{key}: {value}" for key, value in self.style.items()]) + '"'

    def render(self) -> str:
        href_string = f'href="{self.href}"' if self.href else ""
        start_tag = f"<{self.tag} {self.__render_style()} {href_string}".strip() + ">"
        children_html = "".join(
            [child.render() if isinstance(child, HTMLElement) else str(child) for child in self.children]
        )
        end_tag = f"</{self.tag}>"
        return f"{start_tag}{children_html}{end_tag}"

    def __str__(self):
        return self.render()

    @staticmethod
    def h1(child: HTMLElement | str, border_bottom: bool = False) -> HTMLElement:
        return HTMLElement(
            "div",
            children=HTMLElement(
                "h2",
                children=child,
                style=dict(display="inline"),
            ),
            margin_top=1,
            margin_bottom=1,
            padding=0.3,
            background_color="rgba(0,0,0,0.05)",
        )

    @staticmethod
    def h2(child: HTMLElement | str) -> HTMLElement:
        return HTMLElement(
            "div",
            children=HTMLElement(
                "h2",
                children=child,
                style=dict(display="inline"),
            ),
            margin_vertical=1,
            padding=0.3,
            border_bottom=BorderStyle("rgba(0,0,0,0.05)", 3),
        )

    @staticmethod
    def h3(child: HTMLElement | str) -> HTMLElement:
        return HTMLElement(
            "div",
            children=HTMLElement(
                "h3",
                children=child,
                style=dict(display="inline"),
            ),
            margin_vertical=1,
            margin_horizontal=0.5,
        )


class BorderStyle:
    def __init__(self, color: str, width: float):
        self.color = color
        self.width = width

    def render(self) -> str:
        return f"{self.width}px solid {self.color};"


if __name__ == "__main__":
    div = HTMLElement(
        "div",
        style={"display": "flex", "justify-content": "space-between"},
        children=[
            HTMLElement("strong", children="key"),
            HTMLElement("span", children=["value"]),
        ],
    )

    print(div)
