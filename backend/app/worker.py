"""RQ worker entrypoint."""

from redis import Redis
from rq import Worker, Queue, Connection

from app.core.config import settings


def main():
    redis_conn = Redis.from_url(settings.REDIS_URL)
    with Connection(redis_conn):
        worker = Worker(["default"])
        worker.work()


if __name__ == "__main__":
    main()
