import uuid
from typing import TypeVar, cast

import inquirer

T = TypeVar("T")


def prompt_checkbox(choices: list[T], message: str) -> list[T]:
    name = uuid.uuid4()
    questions = [
        inquirer.Checkbox(
            name=name,
            message=message,
            choices=choices,
        )
    ]
    answers = inquirer.prompt(questions)
    if answers is None:
        return []
    if len(answers[name]) == 0:
        return choices
    return cast(list[T], answers[name])


def prompt_radio(choices: list[T], message: str) -> T | None:
    name = uuid.uuid4()
    questions = [
        inquirer.List(
            name=name,
            message=message,
            choices=choices,
        )
    ]
    answers = inquirer.prompt(questions)
    if answers is None:
        return None
    return cast(T, answers[name])
