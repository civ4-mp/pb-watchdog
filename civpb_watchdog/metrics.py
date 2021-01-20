import logging

import pkg_resources

import click_log
from prometheus_client import Counter, Gauge, Info, start_http_server

logger = logging.getLogger(__name__)
click_log.basic_config(logger)

packets_total = Counter(
    "civpb_watchdog_packets_total",
    "Number of observed packets by the Civilization 4 Pitboss watchdog",
    labelnames=("game", "direction"),
)
packets_bytes_total = Counter(
    "civpb_watchdog_packets_bytes_total",
    "Size of observed packets by the Civilization 4 Pitboss watchdog",
    labelnames=("game", "direction"),
)
connections_concurrent = Gauge(
    "civpb_watchdog_connections_active",
    "Number of active connections observed by the Civilization 4 Pitboss watchdog",
    labelnames=("game",),
)
connections_total = Counter(
    "civpb_watchdog_connections_total",
    "Number of connections that were established by the Civilization 4 Pitboss watchdog",
    ("game",),
)
disconnects_total = Counter(
    "civpb_watchdog_forced_disconnects_total",
    "Number of times a connection was forcibly disconnected by the Civilization 4 Pitboss watchdog",
    ("game",),
)
revives_total = Counter(
    "civpb_watchdog_game_revives_total",
    "Number of times a game revive was attempted",
    ("game", "strategy"),
)

capture_errors_total = Counter(
    "civpb_watchdog_capture_errors_total", "Number of capture errors",
)

info = Info("civpb_watchdog", "Civilization 4 Pitboss watchdog version information")
info.info(
    {
        # https://stackoverflow.com/a/2073599/620382
        "version": pkg_resources.require("civpb_watchdog")[0].version,
    }
)


class GameMetrics:
    def __init__(self, game_id):
        self._packets_out = packets_total.labels(game=game_id, direction="out")
        self._packets_in = packets_total.labels(game=game_id, direction="in")
        self._packets_out_bytes = packets_bytes_total.labels(
            game=game_id, direction="out"
        )
        self._packets_in_bytes = packets_bytes_total.labels(
            game=game_id, direction="in"
        )

        self._connections_concurrent = connections_concurrent.labels(game=game_id)
        self._connections_total = connections_total.labels(game=game_id)
        self._disconnects_total = disconnects_total.labels(game=game_id)
        self._game = game_id

    def send(self, size):
        self._packets_out.inc()
        self._packets_out_bytes.inc(size)

    def recv(self, size):
        self._packets_in.inc()
        self._packets_in_bytes.inc(size)

    def connect(self):
        self._connections_total.inc()
        self._connections_concurrent.inc()

    def disconnect(self):
        self._connections_concurrent.dec()

    def force_disconnect(self):
        self._disconnects_total.inc()

    def revive(self, strategy):
        revives_total.labels(game=self._game, strategy=strategy).inc()


def start_metric_server(spec):
    try:
        addr, port = spec.split(":")
        port = int(port)
    except ValueError:
        addr = spec
        port = 9146

    logger.info(f"Starting prometheus server on {addr}:{port}")
    start_http_server(port=port, addr=addr)
