import random

from tv.game import MAX_POWER, POWER_TO, FLY_TO, ENGINES, SHIELDS, LASERS


class BotLogic:
    """
    A bot that just moves randomly and reconfigures the spaceship randomly.
    """
    def initialize(self, map_radius, players, turns, home_base_positions):
        """
        This bot doesn't need to initialize anything.
        """
        pass

    def turn(self, turn_number, hp, ship_number, cargo, position, power_distribution, radar_contacts, leader_board):
        """
        This bot chooses its actions completely at random.
        """
        if random.random() < 0.8:
            # move to a random destination
            speed = power_distribution[ENGINES]
            possible_destinations = list(position.positions_in_range(speed))

            if possible_destinations:
                destination = random.choice(possible_destinations)
                return FLY_TO, destination
        else:
            # randomly distribute power
            power_distribution = {ENGINES: 0, SHIELDS: 0, LASERS: 0}
            for _ in range(MAX_POWER):
                system = random.choice([ENGINES, SHIELDS, LASERS])
                power_distribution[system] += 1

            return POWER_TO, power_distribution
