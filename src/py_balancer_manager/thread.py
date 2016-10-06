import sys
import threading
import logging

logger = logging.getLogger(__name__)


class ClientRefreshRouteThread(threading.Thread):

    exc_info = []

    def __init__(self, client):

        super(ClientRefreshRouteThread, self).__init__()

        self.client = client

    def run(self):

        try:

            self.client.get_routes(refresh=True)

        except Exception as e:

            ClientRefreshRouteThread.exc_info.append(sys.exc_info())
            logger.exception(e)
