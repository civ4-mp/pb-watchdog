import logging
import time
from threading import Lock, Thread

from .connection import Connection

logger = logging.getLogger(__name__)


class ConnectionRegister:
    def __init__(self, packet_limit, cleanup_interval=60):
        self.packet_limit = packet_limit

        self.lock = Lock()
        self._connections = {}
        self._cleanup_interval = cleanup_interval
        # As a daemon thread, this will be cleaned up automatically when the main program ends.
        # Also the main thread will always get the KeyboardInterrupt, so we are fine.
        self._cleanup_thread = Thread(
            target=self._run_cleanup, name="connection cleanup", daemon=True
        )
        logger.debug("starting cleanup thread")
        self._cleanup_thread.start()

    def get(self, client_ip, client_port, server_ip, server_port, now, game):
        # This is more efficient than .get, because then we don"t have to create a useless Client object if
        # Already exists
        connection_id = (client_ip, client_port, server_ip, server_port)
        if connection_id not in self._connections:
            self._connections[connection_id] = Connection(
                client_ip=client_ip,
                client_port=client_port,
                server_ip=server_ip,
                server_port=server_port,
                packet_limit=self.packet_limit,
                now=now,
                game=game,
            )
            game.metrics.connect()
        return self._connections[connection_id]

    def _cleanup(self):
        with self.lock:
            logger.debug(
                "Starting cleanup for {} connections.".format(len(self._connections))
            )
            keys_to_del = []
            for (con_id, con) in self._connections.items():
                logger.debug("{!r}".format(con))
                if not con.is_active():
                    keys_to_del.append(con_id)

            for con_id in keys_to_del:
                self._connections[con_id].game.metrics.disconnect()
                del self._connections[con_id]

    def _run_cleanup(self):
        while True:
            time.sleep(self._cleanup_interval)
            self._cleanup()
