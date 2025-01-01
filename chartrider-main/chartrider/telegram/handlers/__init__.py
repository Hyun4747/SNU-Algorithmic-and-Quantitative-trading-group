from telegram import BotCommand as __BotCommand

from .cmd import command_handler_wrappers as __command_handler_wrappers
from .cmd import command_handlers
from .env import env_handler
from .error import error_handler
from .io import input_handler
from .register import register_secret_handler
from .run import run_handler

bot_commands = [command_handler_wrapper.as_bot_command for command_handler_wrapper in __command_handler_wrappers]
bot_commands += [__BotCommand("switch", "Switch between testnet and mainnet.")]
bot_commands += [__BotCommand("register", "Register a new secret.")]
bot_commands += [__BotCommand("run", "Run the live trading system.")]


__all__ = [
    "bot_commands",
    "command_handlers",
    "env_handler",
    "error_handler",
    "input_handler",
    "register_secret_handler",
    "run_handler",
]
