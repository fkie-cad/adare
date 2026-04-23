# external imports
# logging
import logging

import pandas as pd
from rich.console import Console
from rich.layout import Layout
from rich.rule import ConsoleOptions, Measurement, RenderResult, Rule, cell_len, set_cell_size
from rich.table import Table
from rich.text import Text

log = logging.getLogger(__name__)


class DefaultConsole:
    console: Console

    def __init__(self):
        console = Console()
        # Get the size of the terminal
        terminal_size = console.size
        # Set the height as terminal height minus 10
        desired_height = terminal_size.height - 10 if terminal_size.height > 10 else 1
        self.console = Console(height=desired_height)

    def print(self, layout: Layout):
        self.console.print(layout)


def pad_string_to_length(string: str, length: int, right: bool = True) -> str:
    if len(string) > length:
        return string
    if right:
        return string + ' ' * (length - len(string))
    return ' ' * (length - len(string)) + string


def timedelta_to_str(delta: pd.Timedelta) -> str:
    return str(delta.as_unit('s')) if delta else '...'


class TwoTitleRule(Rule):
    title_right: str
    align: str

    def __init__(self, title: str, style: str, align: str, title_right: str = ''):
        super().__init__(title=title, style=style)
        self.title_right = title_right
        self.align = align

    def __rich_console__(
            self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        width = options.max_width

        characters = (
            "-"
            if (options.ascii_only and not self.characters.isascii())
            else self.characters
        )

        chars_len = cell_len(characters)
        if not self.title:
            yield self._rule_line(chars_len, width)
            return

        title_text = self.title if isinstance(self.title, Text) else console.render_str(self.title, style="rule.text")

        if isinstance(self.title_right, Text):
            title_right_text = self.title_right
        else:
            title_right_text = console.render_str(self.title_right, style="rule.text")

        title_text.plain = title_text.plain.replace("\n", " ")
        title_text.expand_tabs()

        title_right_text.plain = title_right_text.plain.replace("\n", " ")
        title_right_text.expand_tabs()

        required_space = 4 if self.align == "center" else 2
        truncate_width = max(0, width - required_space)
        if not truncate_width:
            yield self._rule_line(chars_len, width)
            return

        rule_text = Text(end=self.end)
        if self.align == "center":
            title_text.truncate(truncate_width, overflow="ellipsis")
            side_width = (width - cell_len(title_text.plain)) // 2
            left = Text(characters * (side_width // chars_len + 1))
            left.truncate(side_width - 1)
            right_length = width - cell_len(left.plain) - cell_len(title_text.plain)
            right = Text(characters * (side_width // chars_len + 1))
            right.truncate(right_length)
            rule_text.append(f"{left.plain} ", self.style)
            rule_text.append(title_text)
            rule_text.append(f" {right.plain}", self.style)
        elif self.align == "left":
            title_text.truncate(truncate_width, overflow="ellipsis")
            rule_text.append(title_text)
            rule_text.append(" ")
            rule_text.append(characters * (width - rule_text.cell_len), self.style)
        elif self.align == "right":
            title_text.truncate(truncate_width, overflow="ellipsis")
            rule_text.append(characters * (width - title_text.cell_len - 1), self.style)
            rule_text.append(" ")
            rule_text.append(title_text)
        elif self.align == "around":
            # place title_text on the left and title_right_text on the right
            title_text.truncate(truncate_width, overflow="ellipsis")
            title_right_text.truncate(truncate_width, overflow="ellipsis")
            rule_text.append(title_text)
            rule_text.append(" ")
            rule_text.append(characters * (width - title_text.cell_len - title_right_text.cell_len - 2), self.style)
            rule_text.append(" ")
            rule_text.append(title_right_text)

        rule_text.plain = set_cell_size(rule_text.plain, width)
        yield rule_text

    def _rule_line(self, chars_len: int, width: int) -> Text:
        rule_text = Text(self.characters * ((width // chars_len) + 1), self.style)
        rule_text.truncate(width)
        rule_text.plain = set_cell_size(rule_text.plain, width)
        return rule_text

    def __rich_measure__(
            self, console: Console, options: ConsoleOptions
    ) -> Measurement:
        return Measurement(1, 1)

class TagsText:
    def __init__(self, tags: str):
        self.tags = tags.split(', ') if tags and tags.strip() else []

    def __rich__(self) -> Table:
        text = ''
        for tag in self.tags:
            if tag.strip():  # Only add non-empty tags
                text += f'[b deep_pink4]#{tag}[/b deep_pink4] '
        text = text[:-1] if text else ''  # Remove trailing space only if text exists
        grid = Table.grid(expand=True)
        grid.add_column(justify="left")
        grid.add_row(
            text,
        )
        return grid
