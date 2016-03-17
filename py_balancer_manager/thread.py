import sys
import threading


class ClientRefreshRouteThread(threading.Thread):

    exc_info = []

    def __init__(self, client):

        super(ClientRefreshRouteThread, self).__init__()

        self.client = client

    def run(self):

        try:

            self.client.get_routes(use_cache=False)

        except Exception as e:

            VmcConnectThread.exc_info.append(sys.exc_info())
