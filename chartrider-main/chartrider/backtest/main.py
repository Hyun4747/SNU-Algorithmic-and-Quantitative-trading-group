import click

from chartrider.strategies import strategy_presets

if __name__ == "__main__":
    click.echo(click.style("\n*** Welcome to Chartrider Backtest! ***\n", fg="bright_blue", bold=True))
    from chartrider.core.backtest.execution.builder import build_handlers_from_prompt

    for handler in build_handlers_from_prompt(strategy_presets):
        handler.run()
