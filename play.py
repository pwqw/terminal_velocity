import sys
from collections import defaultdict

import click

from tv.game import TerminalVelocity
from tv.ui import TerminalVelocityUI


@click.command()
@click.option("--map-radius", type=int, default=12, help="The size of the map, measured as distance from the center to the borders.")
@click.option("--players", type=str, help="Players, specified as a comma separated list of player_name:bot_type.")
@click.option("--turns", type=int, default=100, help="Number of turns to play.")
@click.option("--no-ui", is_flag=True, help="Don't show the ui, just run the game until the end and inform the winner.")
@click.option("--ui-turn-delay", type=float, default=0.2, help="Seconds to wait between turns when showing the ui.")
@click.option("--log-path", type=click.Path(), default="./last_game.log", help="Path for the log file of the game.")
@click.option("--isolated", is_flag=True, help="In isolated mode, bots run inside docker containers and their errors are skipped.")
def main(map_radius, players, turns, no_ui, ui_turn_delay, log_path, isolated):
    """
    Run a game of Terminal Velocity.
    """
    if not players:
        print("No players specified. Use --players option to specify players, e.g. --players Alice:randomaniac,Bob:blind_hunter")
        sys.exit(1)

    # parse the players info
    players_info = {}
    for player_info in players.split(","):
        try:
            name, bot_type = player_info.split(":")
            bot_type = bot_type.lower()
            players_info[name] = bot_type
        except Exception as err:
            raise ValueError(f"Invalid player info: {player_info}. Should be name:bot_type")

    if no_ui:
        ui = None
    else:
        ui = TerminalVelocityUI(ui_turn_delay)

    tv = TerminalVelocity(
        map_radius=map_radius,
        turns=turns,
        players_info=players_info,
        ui=ui,
        log_path=log_path,
        isolated=isolated,
    )

    if ui:
        with ui.show():
            winners = tv.play()
    else:
        winners = tv.play()

    print("Game ended in", turns, "turns!")
    print("Winners:", ",".join(player.name for player in winners))
    print()


if __name__ == '__main__':
    main()
