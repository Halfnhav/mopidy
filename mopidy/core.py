import logging
import multiprocessing

from mopidy import settings
from mopidy.utils import get_class, unpickle_connection

logger = logging.getLogger('mopidy.core')

class CoreProcess(multiprocessing.Process):
    def __init__(self, core_queue):
        multiprocessing.Process.__init__(self)
        self.core_queue = core_queue

    def run(self):
        backend = get_class(settings.BACKENDS[0])(core_queue=self.core_queue)
        frontend = get_class(settings.FRONTEND)(backend=backend)
        while True:
            message = self.core_queue.get()
            if message['command'] == 'mpd_request':
                response = frontend.handle_request(message['request'])
                connection = unpickle_connection(message['reply_to'])
                connection.send(response)
            elif message['command'] == 'end_of_track':
                backend.playback.end_of_track_callback()
            else:
                logger.warning(u'Cannot handle message: %s', message)
