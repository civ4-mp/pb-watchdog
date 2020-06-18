# -*- coding: utf-8 -*-
#!/usr/bin/python3
#
# This script knocking on the port of your Pitboss games to
# find freezed games. Freezed games will be handled with
# the following strategy:
# 1. Simulate mouse click to close popups on virtual x display. (TODO)
# 2. Kill game. The game starting loop should restart the game.
# 3. If 2. fails restart with the previous save game.
#
# Requirements:
# - pip install scapy
#
# Notes:
# - Script requires root/"sudo" to get access to the network traffic or…
# - … you can also use a copy of your python executable and run
#   sudo setcap cap_net_raw=+ep python3
#

import logging
import sys
import time
from datetime import datetime

import click
import toml

import click_config_file
import click_log

# Packet(s) for sniffing
import scapy
from scapy.all import IP, UDP, sniff

from .connection_register import ConnectionRegister
from .game import Game
from .metrics import capture_errors_total, start_metric_server

# Use root logger here, so other loggers inherit the configuration
logger = logging.getLogger()
click_log.basic_config(logger)


class Watchdog:
    def __init__(
        self, ip_address, game_args, packet_limit, script_path, dump_packets,
    ):
        self._script_path = script_path
        self._dump_packets = dump_packets
        self._packet_limit = packet_limit

        self._connections = ConnectionRegister()
        self._games = {}
        for game_arg in game_args:
            game = Game(game_arg, self)
            self._games[game.port]

        self._ip_address = ip_address

    def _handle_packet(self, pkt):
        if not (IP in pkt and UDP in pkt):
            # May be true if some port scanner knocks on PBServer port?!
            # The current traffic filter prevent getting such packets here.
            return

        ip = pkt[IP]
        udp = pkt[UDP]
        payload = udp.payload.original
        now = pkt.time

        if self._dump_packets:
            self._dump_packets.write(
                f"{now}|{ip.src}:{udp.sport}|{ip.dst}:{udp.dport}|{len(payload)}|{payload.hex()}\n"
            )

        with self._connections.lock:
            if ip.src == self._ip_address:
                game = self._games.get(udp.sport)
                self._connections.get(
                    ip.dst, udp.dport, ip.src, udp.sport, now, game
                ).handle_server_to_client(payload, now)
            elif ip.dst == self._ip_address:
                game = self._games.get(udp.dport)
                self._connections.get(
                    ip.src, udp.sport, ip.dst, udp.dport, now, game
                ).handle_client_to_server(payload, now)
            else:
                logger.warning(
                    "PB server matches neither source ({}) nor destination ({})".format(
                        ip.src, ip.dst
                    )
                )

    @property
    def _filter(self):
        f = "udp and ("
        f += " or ".join([game.port for game in self._games])
        f += ")"
        logging.debug(f"Using filter: '{f}'")
        return f

    def analyze_traffic(self, device):
        while True:
            try:
                # With timeout = None and count = 0, this should never complete without an exception
                sniff(
                    prn=self._handle_packet,
                    filter=self._filter,
                    timeout=None,
                    store=0,
                    count=0,
                    iface=device,  # None for sniffing on all.
                )
            except KeyboardInterrupt:
                logger.info("stopping watchdog.")
                return
            except Exception as e:
                logger.error("exception from sniffing: {}".format(e))
            else:
                logger.error("sniff returned normally, this should never happen.")

            capture_errors_total.inc()  # collect metrics
            time.sleep(10)


def toml_provider(file_path, cmd_name):
    return toml.load(file_path)


@click.command()
@click.option(
    "--interface",
    type=str,
    required=True,
    metavar="INTERFACE",
    help="The interface to listen to, e.g., eth0",
)
@click.option(
    "--address",
    type=str,
    required=True,
    metavar="IP",
    help="The IP address used for the PB server.",
)
@click.option(
    "-g",
    "--games",
    type=str,
    required=True,
    multiple=True,
    metavar="GAME",
    help="Altroot directory to a Pitboss game, syntax:\n Path[:Port]\nIf omitted, the port will read from CivilizationIV.ini.",
)
@click.option(
    "-c",
    "--packet-limit",
    metavar="COUNT",
    type=int,
    default=2000,
    help="Number of stray packets after which the client is disconnected.",
)
@click.option(
    "--script-path",
    default=sys.path[0],
    help="path containing civpb-confirm-popup and civpb-kill scripts",
)
@click.option(
    "--prometheus",
    default="",
    help="enable prometheus metrics at given address:port, set to empty to disable",
)
@click.option("--dump-packets", default=None, type=click.File("w+"))
@click.option("--use-pcap/--no-use-pcap", default=False)
@click_config_file.configuration_option(provider=toml_provider, implicit=False)
@click_log.simple_verbosity_option(logger)
def main(
    interface,
    address,
    games,
    packet_limit,
    script_path,
    prometheus,
    dump_packets,
    use_pcap,
):
    if use_pcap:
        scapy.config.conf.use_pcap = True

    if prometheus:
        start_metric_server(prometheus)

    connections = PBNetworkConnectionRegister(packet_limit=packet_limit)

    logger.info("Pitboss upload killer running.")

    if dump_packets:
        logger.info("will dump all packets to file")
        dump_packets.write(f"starting packet dump {datetime.now()}\n")

    watchdog = Watchdog(address, games, packet_limit, script_path, dump_packets)
    watchdog.analyze_udp_traffic(interface)


if __name__ == "__main__":
    main()
