import logging
import socket
import time

# Packets for sending fake client replies
from .pyip import ip as pyip_ip
from .pyip import udp as pyip_udp

logger = logging.getLogger(__name__)


class Connection:
    def __init__(
        self, client_ip, client_port, server_ip, server_port, packet_limit, now, game
    ):
        self.client_ip = client_ip
        self.client_port = client_port
        self.server_ip = server_ip
        self.server_port = server_port

        self.game = game

        self.packet_limit = packet_limit
        self.activity_timeout = 5 * 60

        self.number_unanswered_outgoing_packets = 0
        self.number_unanswered_incoming_packets = 0
        # Just unix timestamps
        self.time_last_outgoing_packet = now
        self.time_last_incoming_packet = now
        self.time_disconnected = None

        # This timestamp will be updated for a subset of all
        # outgoing packages.
        # We assume an active server due the creation of this object
        # to avoid false detection of inactivity.
        # opposed to it's sibling time_last_outgoing_packet, this does not
        # count payload sizes of 5 or 10
        self.time_last_outgoing_active_packet = self.time_last_outgoing_packet

        logger.debug("Detecting new connection {}".format(self))

    def __str__(self):
        return "connection[{}:{}->{}]".format(
            self.client_ip, self.client_port, self.game.game_id
        )

    def __repr__(self):
        s = self.__str__()
        s += "#p: {}, t_in: {}, t_out: {}".format(
            self.number_unanswered_outgoing_packets,
            self.time_last_incoming_packet,
            self.time_last_outgoing_packet,
        )
        if not self.is_active():
            s += " inactive"
        return s

    def handle_server_to_client(self, payload, now):
        self.number_unanswered_outgoing_packets += 1
        self.time_last_outgoing_packet = now

        # Add 28 bytes for UDP (8) and IP headers (20)
        self.game.metrics.send(len(payload) + 28)

        # logger.info("Package from Server, len={}".format( len(payload)))
        # logger.info("Content: {}".format(payload.hex()))

        # == Watchdog functionality ==
        # If the game hangs with a "save error" popup only packages with
        # payload length 3 or 8 will be send. For examples:
        #     (fefe) 640009
        #     (fefe) 0000590009dcdc01
        #     (fefe) 64000a
        #     (fefe) 00005a000adcdc01
        # udp prefix
        #
        # If the game runs normal most idle packages has a
        # payload length of 23, i. e
        # (fefe) 00023b000bfdffffff01ffffffff143f02003d02000001
        #
        # Thus, if we ignore packages with length 3 and 8 we"ve
        # got an indicator for the server sanity.

        if len(payload) not in [5, 10]:
            self.time_last_outgoing_active_packet = self.time_last_outgoing_packet
            self.game.network_reply()

        # TODO Check if we can also use different payload sizes here, but we
        # need to make sure the specific information about the
        # two 16bit numbers "A, B" is available.
        if len(payload) not in [25, 37]:
            return

        # This package could be indicate an upload error. Add the payload
        # for this client (destination IP) to an set. Force analysis
        # of the packages if an sufficient amount of packages reached.
        #
        # The length 35 occurs if the connections was aborted during the loading
        # of a game.

        if self.number_unanswered_outgoing_packets < self.packet_limit:
            return

        # TODO We could also check the time here,
        # but the packet count seems do be the better metric.
        self.disconnect(payload)

    def handle_client_to_server(self, payload, now):
        self.game.metrics.recv(len(payload))

        if self.number_unanswered_outgoing_packets > 100:
            logger.debug(
                "Received client data at {} after {} server packets / {} seconds.".format(
                    self,
                    self.number_unanswered_outgoing_packets,
                    now - self.time_last_incoming_packet,
                )
            )

        # logger.info("Package to Server, len={}".format(len(payload)))

        # Check if server is available. First check guarantee that
        # first package of new client do not produce false positives.
        #
        # Note: This simple approach does only work for periods > 20s!
        # If a single client try to join a blockaded game, at most
        # 20 seconds elapse between two packages.
        if (
            now - self.time_last_incoming_packet < 22
            and now - self.time_last_outgoing_active_packet > 18
        ):
            logger.debug(f"{self!r} - detected no network reply.")
            # TODO (Ramk): Many false positives!
            self.game.no_network_reply()

        self.number_unanswered_outgoing_packets = 0
        self.time_last_incoming_packet = now

    def disconnect(self, payload):
        # TODO Throttle disconnects!
        # Send fake packet to stop upload
        # Structure of content:
        #     254 254 06 B (A+1) (7 bytes)
        #
        # First 2 bytes marks it as udp paket(?!)
        # Thrid bytes is command (close connection to client)
        #   B and A+1 are to 16 bit numbers where A and B
        #   are content of "payload"

        aHi, aLow = payload[3], payload[4]
        bHi, bLow = payload[5], payload[6]
        a_plus_1 = (aHi * 256 + aLow + 1) % 65536

        data = bytes([254, 254, 6, bHi, bLow, int(a_plus_1 / 256), (a_plus_1 % 256)])

        logger.info("Disconnecting client at {!r}".format(self))
        upacket = pyip_udp.Packet()
        upacket.sport = self.client_port
        upacket.dport = self.server_port
        upacket.data = data

        ipacket = pyip_ip.Packet()
        ipacket.src = self.client_ip
        ipacket.dst = self.server_ip
        ipacket.df = 1
        ipacket.ttl = 64
        ipacket.p = 17

        ipacket.data = pyip_udp.assemble(upacket, False)
        raw_ip = pyip_ip.assemble(ipacket, 1)

        # Send fake packet to the PB server that looks like its coming from the client
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
        except socket.error as e:
            logger.error("Socket could not be created: {}".format(e))

        sock.sendto(raw_ip, (ipacket.dst, 0))
        self.time_disconnected = time.time()
        self.number_unanswered_outgoing_packets = 0
        self.game.metrics.force_disconnect()

    def is_active(self):
        now = time.time()
        inactive_time = now - max(
            self.time_last_incoming_packet, self.time_last_outgoing_packet
        )
        return inactive_time < self.activity_timeout
