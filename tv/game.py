import math
import random
import importlib
import logging
from collections import namedtuple
from functools import lru_cache
from itertools import product

from tv.isolation import IsolatedBotLogic

# objects in radar
SPACESHIP = "spaceship"
ASTEROID = "asteroid"
HOME_BASE = "home_base"

# actions
FLY_TO = "fly_to"
POWER_TO = "power_to"
VALID_ACTIONS = (FLY_TO, POWER_TO)

# powered systems
ENGINES = "engines"
SHIELDS = "shields"
LASERS = "lasers"
POWERED_SYSTEMS = (ENGINES, SHIELDS, LASERS)

# balance parameters
MAX_HP = 5
MAX_POWER = 3
MAX_CARGO = 2
HOME_BASE_RADIUS = 2
RADAR_RADIUS = 3
ATTACK_RADIUS = 2
ASTEROIDS_FACTOR = 5


Position = namedtuple("Position", "x y")


class Player:
    """
    A player of the game, with an associated bot logic and game status.
    """
    def __init__(self, name, bot_type, isolated, isolated_turn_timeout):
        self.name = name
        self.bot_type = bot_type

        if isolated:
            self.bot_logic = IsolatedBotLogic(name, bot_type, isolated_turn_timeout)
        else:
            self.bot_logic = Player.import_bot_logic(bot_type)

        self.score = 0
        self.position = None
        self.hp = MAX_HP
        self.cargo = 0
        self.power_distribution = {
            ENGINES: 1,
            SHIELDS: 1,
            LASERS: 1,
        }

    @staticmethod
    def import_bot_logic(bot_type):
        """
        Try to import the bot logic module and instantiate its BotLogic class.
        """
        bot_module = importlib.import_module("bots." + bot_type)

        try:
            bot_class = getattr(bot_module, "BotLogic")
        except AttributeError as err:
            raise ValueError(
                f"Could not find BotLogic class in bot module named {bot_type}. "
                f"Are you sure there's a BotLogic class defined in bots/{bot_type}.py?"
            ) from err

        return bot_class()

    def __str__(self):
        return f"{self.name}:{self.bot_type}"


@lru_cache(maxsize=1000)
def distance(pos_a, pos_b):
    """
    Euclidean distance between two points.
    """
    return math.sqrt(
        abs(pos_a.x - pos_b.x) ** 2
        + abs(pos_a.y - pos_b.y) ** 2
    )


def positions_around(center, radius):
    """
    Gets the positions around a given center up to (including) a certain radius.
    Yields them in shuffled order
    """
    # get possible values for x and y in a rectangle around the center, filter out by distance to
    # only use the ones contained by the circle
    x_values = list(range(center.x - radius, center.x + radius + 1))
    y_values = list(range(center.y - radius, center.y + radius + 1))
    coords_combinations = list(product(x_values, y_values))

    for x, y in coords_combinations:
        position = Position(x, y)
        if distance(center, position) <= radius:
            yield position


class TerminalVelocity:
    """
    A game of Terminal Velocity.

    Game parameters:
    - map_radius: size of the map, measured as distance from the center to the borders
    - turns: how many turns to play
    - players_info: dict with the structure {player name (str): bot type (str)}

    Execution parameters:
    - ui: an instance of an UI to use
    - log_path: path to a file to use as log for this match
    - isolated: bool, if true, players bots will run isolated in docker containers
    - isolated_turn_timeout: when running in isolated mode, the timeout to wait for a response from bots
    """
    def __init__(self, map_radius, turns, players_info,
                 ui=None, log_path=None, isolated=False, isolated_turn_timeout=0.1):
        # initialize players
        self.players = {
            name: Player(name, bot_type, isolated=isolated, isolated_turn_timeout=isolated_turn_timeout)
            for name, bot_type in players_info.items()
        }

        # initialize the rest of the game parameters
        self.map_radius = map_radius
        self.turns = turns
        self.home_base = Position(0, 0)
        self.home_base_positions_cache = set(positions_around(self.home_base, HOME_BASE_RADIUS))
        self.asteroids = set()
        self.required_asteroid_count = ASTEROIDS_FACTOR * len(self.players)

        # execution parameters
        self.ui = ui
        self.isolated = isolated
        self.isolated_turn_timeout = isolated_turn_timeout

        if self.ui:
            self.ui.initialize(self)

        # set up the game log
        logging.basicConfig(
            filename=log_path, level=logging.INFO, filemode="w",
            format="%(asctime)s %(levelname)s %(message)s",
        )
        logging.info("game created with players: %s", players_info)

    def spawn_players(self):
        """
        Spawn any players that aren't already on the map.
        """
        players_positions = self.get_players_positions()
        available_spawn_positions = [
            p for p in self.home_base_positions_cache
            if p not in players_positions
        ]
        random.shuffle(available_spawn_positions)

        for player in self.players.values():
            if not player.position:
                if available_spawn_positions:
                    player.position = available_spawn_positions.pop()
                    player.hp = MAX_HP
                    logging.info("spawned player %s at %s", player.name, player.position)
                else:
                    raise ValueError(f"Not enough space to spawn player {player.name}!")

    def spawn_asteroids(self):
        """
        Spawn new asteroids if the current asteroid count is below the required quantity.
        """
        min_coord = -self.map_radius
        max_coord = self.map_radius

        players_positions = self.get_players_positions()

        while len(self.asteroids) < self.required_asteroid_count:
            position = Position(
                random.randint(min_coord, max_coord),
                random.randint(min_coord, max_coord),
            )

            if distance(self.home_base, position) > HOME_BASE_RADIUS \
                    and position not in self.asteroids \
                    and position not in players_positions:
                self.asteroids.add(position)

    def get_players_positions(self):
        """
        Get the positions of all players currently in the map.
        """
        return set(player.position for player in self.players.values() if player.position)

    def play(self):
        """
        Play the game until the specified turns limit.
        Return the winners at the end (players with the most points).
        """
        try:
            logging.info("starting game loop")
            winners = None

            logging.info("initializing player bots logic")
            for player in self.players.values():
                player.bot_logic.initialize()

            for turn_number in range(self.turns):
                self.spawn_players()
                self.spawn_asteroids()

                players = list(self.players.values())
                random.shuffle(players)
                logging.info("turn %s order: %s", turn_number, ",".join(p.name for p in players))

                for player in players:
                    if not player.hp:
                        # player isn't alive, skip their turn
                        continue

                    turn_ok, reason = self.do_player_action(player)
                    if turn_ok:
                        logging.info("%s action ran ok: %s", player, reason)
                    else:
                        logging.info("%s action failed: %s", player, reason)

                    self.do_player_attacks(player)
                    self.do_player_deliveries(player)

                if self.ui:
                    self.ui.render(turn_number)

            max_score = max(player.score for player in self.players.values())
            winners = [
                player for player in self.players.values()
                if player.score == max_score
            ]
            if winners:
                logging.info("%s won!", " and ".join(winner.name for winner in winners))

            if self.ui:
                self.ui.render(turn_number, winners)
        finally:
            if self.isolated:
                self.isolation_cleanup()

        return winners

    def get_alive_neighbors(self, player, radius):
        """
        Get other players that are alive and at some distance of a given player.
        """
        for other_player in self.players.values():
            # myself
            if other_player is player:
                continue

            # the other player isn't in the map
            if not other_player.position:
                continue

            # the other player is beyond range
            if distance(player.position, other_player.position) > radius:
                continue

            yield other_player

    def get_radar_contacts(self, player):
        """
        Get the list of objects a player can see with its radar.
        """
        contacts = {}

        # add spaceship contacts
        for other_player in self.get_alive_neighbors(player, RADAR_RADIUS):
            contacts[other_player.position] = SPACESHIP

        # add asteroid contacts
        for asteroid in self.asteroids:
            if distance(player.position, asteroid) <= RADAR_RADIUS:
                contacts[asteroid] = ASTEROID

        # add home base contacts
        for home_base_position in self.home_base_positions_cache:
            if distance(player.position, home_base_position) <= RADAR_RADIUS:
                contacts[home_base_position] = HOME_BASE

        return contacts

    def do_player_action(self, player):
        """
        A player takes its turn to play.
        """
        logging.info("%s calling turn() function", player)
        action = player.bot_logic.turn(
            player.hp,
            player.cargo,
            player.position,
            player.power_distribution.copy(),
            self.get_radar_contacts(player),
        )

        if action:
            logging.info("%s requested action: %s", player, action)
        else:
            return False, action

        if not isinstance(action, (list, tuple)) or not len(action) == 2:
            return False, f"{action} does not follow the action format, (action_type, position)"

        action_type, action_argument = action

        if action_type not in VALID_ACTIONS:
            return False, f"unknown action type {action_type}"

        # call the corresponding method to apply the action
        return getattr(self, f"do_action_{action_type}")(player, action_argument)

    def do_action_fly_to(self, player, destination):
        """
        Fly to the specified position.
        """
        if not isinstance(destination, tuple) or not len(destination) == 2:
            return False, f"fly_to destinaton is not a valid position: {destination}"

        if not isinstance(destination, Position):
            destination = Position(*destination)

        speed = max(player.power_distribution[ENGINES] - player.cargo, 0)

        if distance(player.position, destination) > speed:
            return False, f"tried to fly faster than the available power, overheated! {destination}"

        if destination.x < -self.map_radius or destination.x > self.map_radius \
                or destination.y < -self.map_radius or destination.y > self.map_radius:
            return False, f"tried to fly out of the map: {destination}"

        players_positions = self.get_players_positions()
        if destination in players_positions:
            return False, f"tried to fly to a position occupied by another player: {destination}"

        player.position = destination

        # movement should be possible
        grabbed_message = ""
        if destination in self.asteroids:
            # pick up the asteroid if possible
            if player.cargo < MAX_CARGO:
                grabbed_message = ". Grabbed an asteroid!"
                player.cargo += 1
                self.asteroids.remove(destination)

        return True, f"flew to {destination}{grabbed_message}"

    def do_action_power_to(self, player, power_distribution):
        """
        Reconfigure the power distribution of the spaceship.
        """
        if not isinstance(power_distribution, dict) \
            or not len(power_distribution) == 3 \
            or any(system not in power_distribution for system in POWERED_SYSTEMS):
            return False, f"power_to argument is not a valid power distribution: {power_distribution}"

        if sum(power_distribution.values()) > MAX_POWER:
            return False, f"power_to unable to use more power than available in the ship: {power_distribution}"

        player.power_distribution = power_distribution
        return True, f"power_to applied new power distribution: {power_distribution}"

    def do_player_attacks(self, player):
        """
        Do the automatic attacks from the player's spaceship.
        """
        if distance(player.position, self.home_base) <= HOME_BASE_RADIUS:
            # can't attack if I'm in the home base
            return

        damage = player.power_distribution[LASERS]
        targets = self.get_alive_neighbors(player, ATTACK_RADIUS)

        # remove targets that are inside the base, can't be attacked either
        targets = [
            target_player for target_player in targets
            if distance(target_player.position, self.home_base) > HOME_BASE_RADIUS
        ]

        for target_player in targets:
            hit_chance = 1 - 0.2 * target_player.power_distribution[SHIELDS]
            if random.random() < hit_chance:
                target_player.hp = max(0, target_player.hp - damage)

                if target_player.hp:
                    logging.info("%s hit %s for %s damage!", player, target_player, damage)
                else:
                    self.drop_asteroids(target_player.position, target_player.cargo)
                    target_player.position = None
                    target_player.cargo = 0
                    logging.info("%s was destroyed by %s!", target_player, player)
            else:
                logging.info("%s attacked %s but missed!", player, target_player)

    def do_player_deliveries(self, player):
        """
        Do the automatic asteroid delivery at the home base.
        """
        if player.cargo and distance(player.position, self.home_base) <= HOME_BASE_RADIUS:
            delivered_asteroids = player.cargo

            player.score += delivered_asteroids
            player.cargo = 0

            if delivered_asteroids:
                logging.info("%s delivered %s asteroids!", player, delivered_asteroids)

    def drop_asteroids(self, center, count):
        """
        Drop a certain number of asteroids from the player's cargo. Place them in random positions
        around the player.
        """
        for drop_position in positions_around(center, 2):
            if not count:
                break

            if drop_position not in self.asteroids \
                    and drop_position not in self.home_base_positions_cache:
                self.asteroids.add(drop_position)
                count -= 1

    def isolation_cleanup(self):
        """
        Stop the bot logic subprocesses for all players.
        """
        for player in self.players.values():
            player.stop_bot()
