import logging
import os
import time
from enum import Enum, unique

from .metrics import GameMetrics

logger = logging.getLogger(__name__)


@unique
class GameReviveStrategies(Enum):
    NO_STRATEGY = 0
    POPUP_CONFIRM = 1
    RESTART_SAVE = 2
    RESTART_OLD_SAVE = 3
    STOP_PB_SERVER = 4


class Game:
    def __init__(self, altroot_and_port_str, script_path):
        self.script_path = script_path
        path_port = altroot_and_port_str.split(":")

        self.path = path_port[0]
        self.game_id = os.path.basename(os.path.realpath(self.path))

        self.metrics = GameMetrics(self.game_id)

        # Waiting time until next strategy will be used.
        self.strategy_timeout_s = 30
        self.latest_strategy = GameReviveStrategies.NO_STRATEGY
        self.latest_strategy_ts = time.time()

        try:
            self.port = int(path_port[1])
        except IndexError:
            self.port = self.get_port_from_ini(self.path)
        logger.info(
            f"Setup ServerStatus game_id: {self.game_id} path: {self.path} port: {self.port}"
        )
        assert self.port > 0, "game port must be positive"

    @staticmethod
    def get_port_from_ini(path):
        port = None
        ini_path = os.path.join(path, "CivilizationIV.ini")
        try:
            with open(ini_path, "r") as f:
                for line in f:
                    if "Port=" in line[:5]:
                        port = int(line[5:])
                        break
        except IOError:
            logger.warning(
                "Could not read port from {}. Wrong altroot path?".format(ini_path)
            )
        if port is None:
            raise RuntimeError(f"No port found in ini file {ini_path}")
        return port

    # Server is active. Reset civpb_watchdog
    def network_reply(self):
        if self.latest_strategy != GameReviveStrategies.NO_STRATEGY:
            logger.info(
                "Server of game {} is online again. Reset strategies.".format(
                    str(self.game_id)
                )
            )
            self.latest_strategy = GameReviveStrategies.NO_STRATEGY
            self.latest_strategy_ts = (
                time.time()
            )  # Reset on strategy changes only should be fine.

    # Server not responding. Try several awakening strategies.
    def no_network_reply(self):
        now = time.time()
        if (now - self.latest_strategy_ts) < self.strategy_timeout_s:
            return
        self.latest_strategy_ts = now

        if self.latest_strategy == GameReviveStrategies.NO_STRATEGY:
            self.latest_strategy = GameReviveStrategies.POPUP_CONFIRM
            logger.info("Simulate mouse click in game {}.".format(str(self.game_id)))
            self.popup_confirm()
            self.metrics.revive("popup_confirm")
        elif self.latest_strategy == GameReviveStrategies.POPUP_CONFIRM:
            self.latest_strategy = GameReviveStrategies.RESTART_SAVE
            logger.info("Restart game {} with current save.".format(str(self.game_id)))
            self.restart_game(False)
            self.metrics.revive("restart_current_save")
        elif self.latest_strategy == GameReviveStrategies.RESTART_SAVE:
            self.latest_strategy = GameReviveStrategies.RESTART_OLD_SAVE
            logger.info("Restart game {} with previous save.".format(str(self.game_id)))
            self.restart_game(True)
            self.metrics.revive("restart_old_save")
        elif self.latest_strategy == GameReviveStrategies.RESTART_OLD_SAVE:
            self.latest_strategy = GameReviveStrategies.STOP_PB_SERVER
            logger.info(
                "All restart strategies failed. Kill game {} and wait for manual recovery.".format(
                    str(self.game_id)
                )
            )
            self.stop_game()
            self.metrics.revive("stop")

    def popup_confirm(self):
        subprocess.call(
            [os.path.join(self.script_path, "civpb-confirm-popup"), str(self.game_id)]
        )

    def restart_game(self, previous_save=False):
        args = ["-p"] if previous_save else []
        args.append(str(self.game_id))
        subprocess.call([os.path.join(self.script_path, "civpb-kill"), *args])

    def stop_game(self):
        subprocess.call(
            [os.path.join(self.script_path, "civpb-kill"), "-s", str(self.game_id)]
        )
