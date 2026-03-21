import random

from tv.game import ASTEROID, POWER_TO, FLY_TO, ENGINES, SHIELDS, LASERS

class BotLogic:
    """
    A bot that just moves randomly trying to hurt enemies, doesn't care about anything else.
    """
    def initialize(self, map_radius, players, turns, home_base_positions):
        """
        This bot doesn't need to initialize anything.
        """
        pass

    def turn(self, turn_number, hp, ship_number, cargo, position, power_distribution, radar_contacts, leader_board):
        """
        This bot sets up power to the lasers and just moves randomly, expecting to hurt other ships
        in the process.
        """
        desired_distribution = {ENGINES: 1, SHIELDS: 0, LASERS: 2}

        if power_distribution != desired_distribution:
            return POWER_TO, desired_distribution
        else:
            # move to a random destination, but avoid asteroids so we can keep pirating
            asteroid_positions = set(position for position, thing in radar_contacts.items() if thing == ASTEROID)
            # keep trying until you get a clear position
            for destination in position.positions_in_range(1):
                if destination not in asteroid_positions:
                    return FLY_TO, destination
