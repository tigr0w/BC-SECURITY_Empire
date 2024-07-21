import logging

from terminaltables import SingleTable

import empire.client.src.utils.print_util as print_utils
from empire.client.src.EmpireCliConfig import empire_config

log = logging.getLogger(__name__)


def print_table(
    data: list[list[str]] | None = None,
    title: str = "",
    colored_header: bool = True,
    borders: bool | None = None,
    end_space: bool = True,
):
    if data is None:
        return

    if borders is None:
        borders = empire_config.yaml.get("tables", {}).get("borders", True)

    # Make header blue
    if colored_header:
        for x in range(len(data[0])):
            data[0][x] = print_utils.color(data[0][x], "blue")

    table = SingleTable(data)
    table.title = title
    table.inner_row_border = True

    if not borders:
        table.inner_row_border = False
        table.inner_column_border = False
        table.outer_border = False
        table.inner_footing_row_border = False
        table.inner_heading_row_border = False

    print()
    print(table.table)

    if end_space:
        print()


def print_agent_table(
    data: list[list[str]] | None = None,
    formatting: list[list[str]] | None = None,
    title: str = "",
    borders: bool | None = None,
):
    if data is None:
        return

    if borders is None:
        borders = empire_config.yaml.get("tables", {}).get("borders", True)

    # Make header blue
    for x in range(len(data[0])):
        data[0][x] = print_utils.color(data[0][x], "blue")

    for x in range(len(data))[1:]:
        # Add asterisk for high-integrity agents
        if formatting[x][1]:
            data[x][1] = data[x][1] + "*"

        # color agents
        if formatting[x][0]:
            color = "red"
        elif not formatting[x][0]:
            color = "green"

        # Set colors for entire row
        for y in range(len(data[x])):
            data[x][y] = print_utils.color(data[x][y], color)

    table = SingleTable(data)
    table.title = title
    table.inner_row_border = True

    if not borders:
        table.inner_row_border = False
        table.inner_column_border = False
        table.outer_border = False
        table.inner_footing_row_border = False
        table.inner_heading_row_border = False

    print()
    print(table.table)
    print()
