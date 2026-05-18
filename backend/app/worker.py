"""RQ worker entrypoint."""

import logging

from redis import Redis
from rq import Queue, SimpleWorker

from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    redis_conn = Redis.from_url(settings.REDIS_URL)
    queue = Queue("default", connection=redis_conn)
    logger.info("starting RQ simple worker queue=default redis_url=%s", settings.REDIS_URL)
    worker = SimpleWorker([queue], connection=redis_conn)
    worker.work()


if __name__ == "__main__":
    main()
