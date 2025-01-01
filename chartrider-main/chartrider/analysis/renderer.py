from collections import defaultdict
from itertools import cycle
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import numpy as np
from bokeh.events import RangesUpdate
from bokeh.layouts import column, gridplot
from bokeh.models import (
    ColumnDataSource,
    CustomJS,
    Div,
    HoverTool,
    Model,
    Range1d,
    Span,
    WheelZoomTool,
)
from bokeh.models.axes import LinearAxis
from bokeh.models.formatters import NumeralTickFormatter
from bokeh.models.ranges import DataRange1d
from bokeh.models.tools import CrosshairTool
from bokeh.palettes import Category10
from bokeh.plotting import figure

from chartrider.analysis.datasource import (
    PlotDataSource,
    SignpostData,
    StrategyDataSource,
    SymbolDataSource,
    as_datetime_array,
)
from chartrider.analysis.resampler import ResampledDataProvider
from chartrider.core.strategy.signpost import Signpost
from chartrider.utils.data import Indicator
from chartrider.utils.htmlsnippets import HTMLElement
from chartrider.utils.prettyprint import PrettyPrintMode
from chartrider.utils.timeutils import TimeUtils


class BokehPlotRenderer:
    TOOLS = ["xpan", "xwheel_zoom", "reset", "save"]
    BACKGROUND_COLOR = "#FCFCFC"
    RED = "#E35461"
    GREEN = "#5EBA89"
    YELLOW = "#F4B701"
    BLUE = "#26547C"

    def __init__(self, datasource: PlotDataSource) -> None:
        self.datasource = datasource

        self.datetime_array = as_datetime_array(datasource.timestamp_array)
        start = self.datetime_array[0]
        end = self.datetime_array[-1]
        pad = (end - start) * 0.05
        self.x_range = Range1d(
            start=start - pad / 2,
            end=end + pad / 2,
            min_interval=1000 * 60 * 100,
            bounds=(start - pad, end + pad),
        )
        self.provider = ResampledDataProvider(data_source=datasource, x_range=cast(Range1d, self.x_range))

    def __autoscale_callback(
        self,
        high: np.ndarray,
        low: np.ndarray | None,
        y_range: Model,
    ) -> Model:
        """
        Returns a CustomJS callback that autoscales the y axis to fit the data.
        """
        callback_path = Path(__file__).parent / "js" / "autoscale_callback.js"
        with open(callback_path, encoding="utf-8") as f:
            js_code = f.read().replace(
                "$id",
                str(uuid4()),
            )

        first_non_nan_index = np.argmax(~np.isnan(self.datasource.timestamp_array))
        return CustomJS(
            args=dict(
                high=high,
                low=low,
                resample_freq_min=self.datasource.resample_freq_min,
                y_range=y_range,
                min_timestamp=self.datasource.timestamp_array[first_non_nan_index],
            ),
            code=js_code,
        )

    def __dynamic_tooltip_callback(
        self,
        ends_with: str,
        hovertool: Model,
        source: Model,
    ) -> Any:
        """
        Returns a CustomJS callback that updates the hovertool's tooltips based on the available fields.
        """
        callback_path = Path(__file__).parent / "js" / "dynamic_tooltip_callback.js"
        with open(callback_path, encoding="utf-8") as f:
            js_code = f.read().replace(
                "$endsWith",
                ends_with,
            )

        return CustomJS(
            args=dict(
                hover=hovertool,
                source=source,
            ),
            code=js_code,
        )

    def __make_figure(
        self,
        height: int,
        title: str | None = None,
        y_label: str | None = None,
        show_x_axis: bool = True,
        autorange_y_axis: bool = True,
    ):
        options = dict()
        if not autorange_y_axis:
            options["y_range"] = Range1d()
        fig = figure(
            title=title,
            height=height,
            x_axis_type="datetime",
            x_axis_location="below" if show_x_axis else None,
            x_range=self.x_range,
            y_axis_label=y_label,
            background_fill_color=self.BACKGROUND_COLOR,
            sizing_mode="stretch_width",
            tools=",".join(self.TOOLS),
            **options,
        )
        # Remove logo
        fig.toolbar.logo = None  # type: ignore

        # Force wheel zoom to not maintain focus
        wheelzoom_tool = next(wz for wz in fig.tools if isinstance(wz, WheelZoomTool))
        wheelzoom_tool.maintain_focus = False  # type: ignore

        fig.yaxis[0].formatter = NumeralTickFormatter(format="0a")
        return fig

    def __div_title(self) -> Model:
        title = div_widget(
            text=HTMLElement(
                "div",
                children=[
                    HTMLElement("h1", self.datasource.name, margin_bottom=0.5),
                    HTMLElement("pre", self.datasource.description),
                ],
            ).render(),
        )
        return title

    def __div_stat_result(self) -> Model:
        stat_html = self.datasource.stat.format(mode=PrettyPrintMode.full_html)
        overview = div_widget(
            text=HTMLElement(
                "div",
                children=[
                    HTMLElement("div", stat_html),
                ],
                margin_bottom=1,
            ).render()
        )
        return overview

    def __make_strategy_plots(self) -> list[Model]:
        plots = []
        for strategy in self.datasource.strategy_sources:
            plots.extend(self.__make_strategy_plot(strategy))
        return plots

    def __make_strategy_plot(self, strategy_datasource: StrategyDataSource) -> list[Model]:
        plots = []
        strategy_title = div_widget(
            text=HTMLElement.h1(
                HTMLElement(
                    "span",
                    [
                        strategy_datasource.strategy_name,
                        HTMLElement(
                            "code",
                            f" ({strategy_datasource.strategy_slug})",
                            style={"font-weight": "normal"},
                        ),
                    ],
                )
            ).render(),
        )
        plots.append(strategy_title)
        for symbol_datasource in strategy_datasource.symbol_sources:
            ohlcv_plot = self.__make_ohlc_plot(strategy_datasource, symbol_datasource)
            volume_plot = self.__make_volume_plot(symbol_datasource)
            indicator_plots = self.__make_supplementary_indicator_plots(strategy_datasource, symbol_datasource)
            pnl_plot = self.__make_pnl_plot(symbol_datasource, strategy_datasource)
            position_plot = self.__make_position_plot(symbol_datasource)
            plots.extend([ohlcv_plot, volume_plot, *indicator_plots, pnl_plot, position_plot])
        plots = [plot for plot in plots if plot is not None]
        return plots

    def __make_equity_plot(self) -> list[Model]:
        title = div_widget(text=HTMLElement.h1("Equity").render())
        equity_plot = self.__make_figure(height=250, y_label="Equity")
        first_non_nan_index = np.argmax(~np.isnan(self.datasource.equity_history))

        def cds_data() -> dict:
            return {
                "datetime": self.provider.datetime_array(),
                "datestring": self.provider.datestring_array(),
                "equity": self.provider.equity_history(),
                "running_max": self.provider.running_max(),
            }

        source = ColumnDataSource(data=cds_data())
        equity_plot.on_event(RangesUpdate, lambda: source.data.update(cds_data()))

        equity_line = equity_plot.line(
            x="datetime",
            y="equity",
            source=source,
            color=self.BLUE,
            line_width=1.2,
        )

        # Calculate values for final, peak, and max drawdown points
        original_equity_history = self.datasource.equity_history
        original_datetime = self.datasource.timestamp_array
        final_value = original_equity_history[-1]
        peak_index = np.nanargmax(original_equity_history)
        peak_value = original_equity_history[peak_index]
        running_max = np.fmax.accumulate(original_equity_history)
        drawdowns = 1 - original_equity_history / running_max
        max_drawdown_index = np.nanargmax(drawdowns)
        mdd_percent = (self.datasource.stat.max_drawdown or 0) * 100
        first_non_nan_index = np.argmax(~np.isnan(self.datasource.equity_history))
        initial_value = original_equity_history[first_non_nan_index]
        final_percent_change = ((final_value - initial_value) / initial_value + 1) * 100
        peak_percent_change = ((peak_value - initial_value) / initial_value + 1) * 100

        # # Running Max Line
        equity_plot.line(
            x="datetime",
            y="running_max",
            color=self.YELLOW,
            alpha=0.5,
            source=source,
        )
        equity_plot.varea(
            x="datetime",
            y1="running_max",
            y2="equity",
            color=self.YELLOW,
            alpha=0.1,
            source=source,
        )

        # Final Point
        equity_plot.circle(
            x=original_datetime[-1],
            y=final_value,
            color=self.BLUE,
            size=8,
            legend_label=f"Final ({final_percent_change:.2f}%)",
            line_color=(0, 0, 0, 0.3),
        )

        # Peak Point
        equity_plot.circle(
            x=original_datetime[peak_index],
            y=peak_value,
            color=self.GREEN,
            size=8,
            legend_label=f"Peak ({peak_percent_change:.2f}%)",
            line_color=(0, 0, 0, 0.3),
        )

        # # Max Drawdown Point
        equity_plot.circle(
            x=original_datetime[max_drawdown_index],
            y=original_equity_history[max_drawdown_index],
            color=self.RED,
            size=8,
            legend_label=f"Max Drawdown ({mdd_percent:.2f}%)",
            line_color=(0, 0, 0, 0.3),
        )

        tooltips = [
            ("Date", "@datestring"),
            ("Equity", "@equity{0.00}"),
        ]
        equity_plot.add_tools(hovertool(tooltips=tooltips, mode="vline", renderers=[equity_line]))
        return [title, equity_plot]

    def __make_ohlc_plot(
        self,
        strategy_datasource: StrategyDataSource,
        symbol_datasource: SymbolDataSource,
    ) -> Model:
        ohlc_plot = self.__make_figure(
            height=250,
            y_label="OHLC",
            show_x_axis=False,
            title=symbol_datasource.symbol.base_currency,
            autorange_y_axis=False,
        )

        def cds_data() -> dict:
            symbol_data = self.provider.symbol_datasource(symbol_datasource)
            data_dict = {
                "datetime": self.provider.datetime_array(),
                "datestring": self.provider.datestring_array(),
                "high": symbol_data.high,
                "low": symbol_data.low,
                "open": symbol_data.open,
                "close": symbol_data.close,
                "color": np.where(symbol_data.close > symbol_data.open, self.GREEN, self.RED),
            }
            for indicator in self.provider.indicators(strategy_datasource):
                if not indicator.plot or indicator.name is None:
                    continue
                if indicator.figure_id is not None:
                    continue
                data_dict[indicator.name] = indicator.original_indicator[symbol_datasource.symbol].as_array()
            return data_dict

        source = ColumnDataSource(data=cds_data())

        high_max = source.data["high"].max()  # type: ignore
        low_min = source.data["low"].min()  # type: ignore
        pad = (high_max - low_min) * 0.05
        ohlc_plot.y_range.start = low_min - pad
        ohlc_plot.y_range.end = high_max + pad

        ohlc_plot.segment(
            x0="datetime",
            y0="high",
            x1="datetime",
            y1="low",
            color="color",
            source=source,
        )

        ohlc_vbar = ohlc_plot.vbar(
            x="datetime",
            width=self.provider.candlestick_width() * 0.9,
            top="open",
            bottom="close",
            fill_color="color",
            line_width=0,
            source=source,
        )

        def on_range_update() -> None:
            data = cds_data()
            source.data = data
            ohlc_vbar.glyph.width = self.provider.candlestick_width() * 0.9  # type: ignore

        ohlc_plot.on_event(RangesUpdate, on_range_update)

        tooltips = [
            ("Date", "@datestring"),
            ("Open", "@open{0.00}"),
            ("High", "@high{0.00}"),
            ("Low", "@low{0.00}"),
            ("Close", "@close{0.00}"),
        ]

        self.__add_signposts(
            ohlc_plot,
            strategy_datasource.signposts_by_symbol(symbol=symbol_datasource.symbol),
            symbol_datasource,
        )
        self.__add_indicators(
            base_plot=ohlc_plot,
            indicators=strategy_datasource.indicators,
            column_datasource=cast(ColumnDataSource, source),
            tooltip=tooltips,
        )

        ohlc_plot.x_range.js_on_change(
            "end",
            self.__autoscale_callback(
                high=symbol_datasource.high,
                low=symbol_datasource.low,
                y_range=ohlc_plot.y_range,
            ),  # type: ignore
        )

        hover_tool = hovertool(
            tooltips=tooltips,
            mode="vline",
            renderers=[ohlc_vbar],
        )
        ohlc_plot.add_tools(hover_tool)

        return ohlc_plot

    def __add_indicators(
        self,
        base_plot: Model,
        indicators: list[Indicator],
        column_datasource: ColumnDataSource,
        tooltip: list[tuple[str, str]],
        figure_id: int | None = None,
    ) -> None:
        def palette():
            yield from cycle(Category10[10])

        colors = palette()

        for indicator in indicators:
            if not indicator.plot or indicator.name is None:
                continue
            if indicator.figure_id != figure_id:
                continue
            color = next(colors)
            tooltip.append((indicator.name, f"@{indicator.name}{{0.00}}"))
            base_plot.line(
                "datetime",
                indicator.name,
                line_color=color,
                legend_label=indicator.name,
                line_width=1.5,
                alpha=0.7,
                source=column_datasource,
            )

    def __make_supplementary_indicator_plots(
        self, strategy_datasource: StrategyDataSource, symbol_datasource: SymbolDataSource
    ) -> list[Model]:
        # Group indicators by figure_id
        indicators_by_figure_id = defaultdict(list)
        for indicator in strategy_datasource.indicators:
            if indicator.figure_id is None:
                continue
            indicators_by_figure_id[indicator.figure_id].append(indicator)

        # Create a plot for each group of indicators
        plots = []
        for figure_id, indicators in indicators_by_figure_id.items():
            indicator_plot = self.__make_figure(height=100, y_label=f"Figure {figure_id}", show_x_axis=False)

            def cds_data() -> dict:
                data_dict = {
                    "datetime": self.provider.datetime_array(),
                    "datestring": self.provider.datestring_array(),
                }

                for indicator in self.provider.indicators(strategy_datasource):
                    if not indicator.plot or indicator.name is None:
                        continue
                    if indicator.figure_id != figure_id:
                        continue
                    data_dict[indicator.name] = indicator.original_indicator[symbol_datasource.symbol].as_array()
                return data_dict

            source = ColumnDataSource(data=cds_data())

            def on_range_update() -> None:
                data = cds_data()
                source.data = data
                indicator_plot.y_range.start = min(data[indicator.name].min() for indicator in indicators)
                indicator_plot.y_range.end = max(data[indicator.name].max() for indicator in indicators)

            indicator_plot.on_event(RangesUpdate, on_range_update)

            tooltips: list[tuple[str, str]] = [("Date", "@datestring")]
            self.__add_indicators(
                base_plot=indicator_plot,
                indicators=indicators,
                column_datasource=cast(ColumnDataSource, source),
                tooltip=tooltips,
                figure_id=figure_id,
            )
            plots.append(indicator_plot)
            hover_tool = hovertool(
                tooltips=tooltips,
                mode="vline",
                renderers=[indicator_plot.renderers[0]],  # type: ignore
            )
            indicator_plot.add_tools(hover_tool)

        return plots

    def __add_signposts(
        self,
        ohlc_plot: Model,
        signposts: SignpostData,
        symbol_datasource: SymbolDataSource,
    ) -> None:
        def convert_signpost_to_datapoint(begin: Signpost, end: Signpost | None = None):
            begin_price = symbol_datasource.get_close_price(begin.timestamp)
            data = {
                "x0": begin.timestamp,
                "y0": float(begin_price),
                "date0": TimeUtils.timestamp_to_datestring(begin.timestamp),
                "name0": begin.name,
                "description0": begin.description,
                **{key + "0": value for key, value in begin.info.items()},
            }

            if end:
                end_price = symbol_datasource.get_close_price(end.timestamp)
                data.update(
                    {
                        "x1": end.timestamp,
                        "y1": float(end_price),
                        "date1": TimeUtils.timestamp_to_datestring(end.timestamp),
                        "name1": end.name,
                        "description1": end.description,
                        "colors": self.GREEN if begin_price < end_price else self.RED,
                        **{key + "1": value for key, value in end.info.items()},
                    }
                )
            return data

        interval_data = [
            convert_signpost_to_datapoint(begin, end)
            for signposts_list in signposts.values()
            for begin, end in zip([signposts_list[0]] * len(signposts_list[1:]), signposts_list[1:])
            if len(signposts_list[1:]) != 0
        ]
        interval_data_all_keys = set(key for d in interval_data for key in d.keys())
        event_data = [
            convert_signpost_to_datapoint(event)
            for signposts_list in signposts.values()
            for event in signposts_list
            if len(signposts_list) == 1
        ]
        event_data_all_keys = set(key for d in event_data for key in d.keys())

        # Interval signposts
        if len(interval_data) > 0:
            interval_source = ColumnDataSource({k: [d.get(k) for d in interval_data] for k in interval_data_all_keys})
            ohlc_plot.segment(color="colors", line_width=8, line_dash="dotted", source=interval_source)
            circles0 = ohlc_plot.circle(
                x="x0", y="y0", size=6, source=interval_source, fill_color="colors", line_color=(0, 0, 0, 0.3)
            )
            circles1 = ohlc_plot.circle(
                x="x1", y="y1", size=6, source=interval_source, fill_color="colors", line_color=(0, 0, 0, 0.3)
            )
            start_tooltip = hovertool(renderers=[circles0])
            start_tooltip.callback = self.__dynamic_tooltip_callback(
                ends_with="0", hovertool=start_tooltip, source=interval_source
            )
            end_tooltip = hovertool(renderers=[circles1])
            end_tooltip.callback = self.__dynamic_tooltip_callback(
                ends_with="1", hovertool=end_tooltip, source=interval_source
            )
            ohlc_plot.add_tools(start_tooltip, end_tooltip)

        # Event signposts
        if len(event_data) > 0:
            event_source = ColumnDataSource({k: [d.get(k) for d in event_data] for k in event_data_all_keys})
            events = ohlc_plot.circle(
                x="x0", y="y0", size=6, source=event_source, fill_color=self.YELLOW, line_color=(0, 0, 0, 0.3)
            )
            event_tooltip = hovertool(renderers=[events])
            event_tooltip.callback = self.__dynamic_tooltip_callback(
                ends_with="0", hovertool=event_tooltip, source=event_source
            )
            ohlc_plot.add_tools(event_tooltip)

    def __make_volume_plot(self, symbol_datasource: SymbolDataSource) -> Model:
        volume_plot = self.__make_figure(
            height=80,
            y_label="Volume",
            show_x_axis=False,
        )

        def cds_data() -> dict:
            symbol_data = self.provider.symbol_datasource(symbol_datasource)
            return {
                "datetime": self.provider.datetime_array(),
                "datestring": self.provider.datestring_array(),
                "volume": symbol_data.volume,
                "color": np.where(symbol_data.close > symbol_data.open, self.GREEN, self.RED),
            }

        source = ColumnDataSource(data=cds_data())

        volume_vbar = volume_plot.vbar(
            x="datetime",
            top="volume",
            width=self.provider.candlestick_width() * 0.9,
            fill_color="color",
            line_width=0,
            fill_alpha=0.7,
            source=source,
        )

        def on_range_update() -> None:
            data = cds_data()
            volume_vbar.glyph.width = self.provider.candlestick_width() * 0.9  # type: ignore
            source.data = data
            volume_plot.y_range.start = 0
            volume_plot.y_range.end = data["volume"].max() * 1.1

        volume_plot.on_event(RangesUpdate, on_range_update)

        tooltips = [
            ("Date", "@datestring"),
            ("Volume", "@volume{0.00}"),
        ]

        hover_tool = hovertool(
            tooltips=tooltips,
            mode="vline",
        )

        volume_plot.add_tools(hover_tool)
        return volume_plot

    def __make_pnl_plot(
        self,
        symbol_datasource: SymbolDataSource,
        strategy_datasource: StrategyDataSource,
    ) -> Model | None:
        # Filter trades for the given symbol
        symbol_trades = [trade for trade in strategy_datasource.trades if trade.symbol == symbol_datasource.symbol]

        realized_pnls = np.abs(np.array([float(trade.realizedPnl) for trade in symbol_trades]))

        def color(realized_pnl: float):
            if realized_pnl > 0:
                return self.GREEN
            elif realized_pnl < 0:
                return self.RED
            else:
                return (0, 0, 0, 0.1)

        def marker(realized_pnl: float) -> str:
            if realized_pnl > 0:
                return "triangle"
            elif realized_pnl < 0:
                return "inverted_triangle"
            else:
                return "circle_cross"

        if len(symbol_trades) == 0:
            return None

        source = ColumnDataSource(
            data={
                "timestamp": [trade.timestamp for trade in symbol_trades],
                "datetime": [TimeUtils.timestamp_to_datestring(trade.timestamp) for trade in symbol_trades],
                "realizedPnlPercent": [trade.realizedPnlPercent for trade in symbol_trades],
                "realizedPnl": [float(trade.realizedPnl) for trade in symbol_trades],
                "fee": [float(trade.fee.cost) for trade in symbol_trades],
                "amount": [float(trade.amount) for trade in symbol_trades],
                "color": [color(trade.realizedPnl) for trade in symbol_trades],
                "markerSize": np.interp(
                    realized_pnls,
                    (
                        np.nanmin(realized_pnls),
                        np.nanmax(realized_pnls),
                    ),
                    (8, 20),
                ),
                "marker": [marker(trade.realizedPnl) for trade in symbol_trades],
            }
        )
        pnl_plot = self.__make_figure(height=80, y_label="Trades", show_x_axis=False)
        pnl_plot.scatter(
            x="timestamp",
            y="realizedPnlPercent",
            color="color",
            size="markerSize",
            marker="marker",
            line_color=(0, 0, 0, 0.5),
            source=source,
        )

        # Adjust y range with padding
        pnl_percents = source.data["realizedPnlPercent"]
        min_pnl_percent = np.nanmin(pnl_percents) * 2
        max_pnl_percent = np.nanmax(pnl_percents) * 2
        pnl_plot.y_range.start = min(0, min_pnl_percent)
        pnl_plot.y_range.end = max(0, max_pnl_percent)

        tooltips = [
            ("Date", "@datetime"),
            ("Percent", "@realizedPnlPercent{0.2f}%"),
            ("Amount", "@amount{0.00}"),
            ("PnL", "@realizedPnl{$0,0.00}"),
            ("Fee", "@fee{$0,0.00}"),
        ]
        hover_tool = hovertool(tooltips=tooltips)
        pnl_plot.add_tools(hover_tool)

        return pnl_plot

    def __make_position_plot(
        self,
        symbol_datasource: SymbolDataSource,
    ) -> Model:
        position_plot = self.__make_figure(height=100, y_label="Position")
        position_plot.yaxis[0].visible = False

        def cds_data() -> dict:
            symbol_data = self.provider.symbol_datasource(symbol_datasource)
            return {
                "datetime": self.provider.datetime_array(),
                "datestring": self.provider.datestring_array(),
                "long_amount": symbol_data.long_amount_history,
                "short_amount": symbol_data.short_amount_history,
                "long_notional": symbol_data.long_notional_history,
                "short_notional": symbol_data.short_notional_history,
            }

        source = ColumnDataSource(data=cds_data())
        position_plot.on_event(RangesUpdate, lambda: source.data.update(cds_data()))

        # Function to add lines to the plot
        def add_line(y_column: str, color: str, y_range_name: str):
            is_notional = y_column.endswith("notional")
            return position_plot.line(
                x="datetime",
                y=y_column,
                color=color,
                y_range_name=y_range_name,
                source=source,
                alpha=0.4 if is_notional else 1,
            )

        # Setup DataRange and Axis for amount and notional
        for name in ["amount", "notional"]:
            datarange = DataRange1d()
            position_plot.extra_y_ranges[name] = datarange  # type: ignore
            position_plot.add_layout(
                LinearAxis(
                    y_range_name=name,
                    axis_label=name.capitalize(),
                    formatter=NumeralTickFormatter(format="0a"),
                ),
                "right" if name == "notional" else "left",
            )
            datarange.renderers.extend(  # type: ignore
                [
                    add_line(f"long_{name}", self.GREEN, name),
                    add_line(f"short_{name}", self.RED, name),
                ]
            )

        tooltips = [
            ("Date", "@datestring"),
            ("Long Amount", "@long_amount{0.00}"),
            ("Short Amount", "@short_amount{0.00}"),
            ("Long Notional", "@long_notional{0.00}"),
            ("Short Notional", "@short_notional{0.00}"),
        ]
        hover_tool = hovertool(tooltips=tooltips, mode="vline", renderers=[position_plot.renderers[0]])  # type: ignore
        position_plot.add_tools(hover_tool)

        return position_plot

    def __post_configure_plots(self, plots: list[Model]):
        """
        Some plots need to be configured after they are created and populated with data.
        """
        vertical_span = Span(dimension="height", line_width=1)
        for fig in plots:
            if not isinstance(fig, figure):
                continue
            if fig.legend:
                fig.legend.location = "top_left"
                fig.legend.click_policy = "hide"

            horizontal_span = Span(dimension="width", line_width=1)
            linked_crosshair = CrosshairTool(overlay=(vertical_span, horizontal_span), toggleable=False)
            fig.add_tools(linked_crosshair)  # type: ignore

    def create_plot(self):
        title = self.__div_title()
        equity = self.__make_equity_plot()
        strategy_plots = self.__make_strategy_plots()
        stat_result = self.__div_stat_result()
        plots = [title, *equity, *strategy_plots, stat_result]
        self.__post_configure_plots(plots)
        grid = gridplot(
            plots,  # type: ignore
            ncols=1,
            toolbar_location="above",
            sizing_mode="stretch_width",
            merge_tools=True,
        )
        vstack = column(children=[grid], sizing_mode="stretch_width", margin=(0, 50, 0, 50))
        return vstack


def hovertool(
    tooltips: list[tuple[str, str]] = [],
    mode: str = "mouse",
    renderers: list[Model] | None = None,
) -> HoverTool:
    return HoverTool(
        tooltips=tooltips,
        mode=mode,
        renderers=renderers or "auto",
        toggleable=False,
    )  # type: ignore


def div_widget(text: str, margin: int | tuple[int, int, int, int] | None = None) -> Div:
    return Div(
        text=text,
        sizing_mode="stretch_width",
        stylesheets=[".bk-clearfix { display: block !important; }"],
        margin=margin or 0,
    )  # type: ignore
