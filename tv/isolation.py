import json
import subprocess
import time

import zmq


TURN_TIMEOUT = 1000  # ms
INITIALIZE_TIMEOUT = 3000  # ms


class RemoteBotError(Exception):
    """
    The remote bot raised an error when trying to execute a method call.
    """
    pass


class RemoteBotTimmeout(TimeoutError):
    """
    The remote bot took too long to respond to a method call.
    """
    pass


class RemoteBotLogicClient:
    """
    A 'bot' that in reality spawns a docker container with the actual bot running inside it.
    """
    # this will be incremented automatically each time we start a new remote bot
    LAST_USED_PORT = 5000

    def __init__(self, bot_type):
        self.bot_type = bot_type
        self.port = None
        self.bot_server_process = None

    def initialize(self, player_name, map_radius, players, turns, home_base_positions):
        """
        Initialize the bot running inside the container.
        """
        self.remote_call("initialize", {
            "player_name": player_name,
            "map_radius": map_radius,
            "players": players,
            "turns": turns,
            "home_base_positions": [(p.x, p.y) for p in home_base_positions],
        }, INITIALIZE_TIMEOUT)

    def turn(self, turn_number, hp, ship_number, cargo, position, power_distribution, radar_contacts, leader_board):
        """
        Ask the bot in the container for an action and return it.
        """
        return self.remote_call("turn", {
            "turn_number": turn_number,
            "hp": hp,
            "ship_number": ship_number,
            "cargo": cargo,
            "position": (position.x, position.y),
            "power_distribution": power_distribution,
            "radar_contacts": {f"{p.x},{p.y}": thing for p, thing in radar_contacts.items()},
            "leader_board": leader_board,
        }, TURN_TIMEOUT)

    def start_bot_server(self):
        """
        Start the docker container running the bot logic.
        """
        self.port = RemoteBotLogicClient.LAST_USED_PORT + 1
        RemoteBotLogicClient.LAST_USED_PORT = self.port

        # docker run bot-server --bot-type <type> --port <port>
        self.bot_server_process = subprocess.Popen(
            f"docker run -p {self.port}:5000 terminal-velocity-bot-server --bot-type {self.bot_type} --port 5000",
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            shell=True,
        )

    def stop_bot_server(self):
        """
        Stop the docker container running the bot logic.
        """
        self.bot_server_process.kill()

    def remote_call(self, method_name, kw_args, timeout):
        """
        Call a method on the remote bot.
        """
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.setsockopt(zmq.RCVTIMEO, timeout)
        socket.connect(f"tcp://localhost:{self.port}")

        socket.send_string(json.dumps({"method_name": method_name, "kw_args": kw_args}))
        try:
            result = json.loads(socket.recv())
        except zmq.Again as err:
            raise RemoteBotTimmeout() from err

        if result["worked"]:
            return result["return_value"]
        else:
            raise RemoteBotError(result["error"])


def bot_server(bot_type, port):
    """
    A server that uses an internal bot to answer remote method calls.
    This runs inside the containers.
    """
    print("creating zmq server")

    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind(f"tcp://*:{port}")

    from tv.game import Player, Position  # noqa avoid circular import
    bot_logic = Player.import_bot_logic(bot_type)

    print("starting server loop")

    while True:
        # each time we get a new message, call the requested method and return
        # the result
        message = json.loads(socket.recv())
        print("message received!", message)

        try:
            method_name = message["method_name"]
            kw_args = message["kw_args"]

            # parse the arguments, converting the special cases
            if method_name == "initialize":
                # convert home base positions to Position objects
                kw_args["home_base_positions"] = [
                    Position(x, y) for x, y in kw_args["home_base_positions"]
                ]
            elif method_name == "turn":
                # convert position to Position object
                kw_args["position"] = Position(*kw_args["position"])
                # convert radar contact positions to Position objects
                kw_args["radar_contacts"] = {
                    Position(*map(int, pos.split(","))): thing
                    for pos, thing in kw_args["radar_contacts"].items()
                }

            print("calling method", method_name)
            bot_result = getattr(bot_logic, method_name)(**kw_args)

            print("method", method_name, "returned", bot_result)
            result = {"worked": True, "return_value": bot_result}
        except Exception as err:
            print("method", method_name, "raised an error:", err)
            result = {"worked": False, "error": str(err)}

        print("sending result")
        socket.send_string(json.dumps(result))
