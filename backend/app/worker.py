"""RQ worker entrypoint."""

import argparse
import logging
from multiprocessing import Process

from redis import Redis
from rq import Queue, SimpleWorker

from app.config import settings

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    for logger_name in ("httpx", "httpcore", "openai"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def _work(queue_name: str) -> None:
    _configure_logging()
    redis_conn = Redis.from_url(settings.REDIS_URL)
    queue = Queue(queue_name, connection=redis_conn)
    logger.info(
        "starting RQ simple worker queue=%s redis_url=%s",
        queue_name,
        settings.REDIS_URL,
    )
    worker = SimpleWorker([queue], connection=redis_conn)
    worker.work()


def main():
    parser = argparse.ArgumentParser(description="Run Paper Search RQ workers")
    parser.add_argument("--queue", default="default", help="RQ queue name to listen on")
    parser.add_argument(
        "--num-workers",
        type=int,
        default=1,
        help="Number of worker processes to start",
    )
    args = parser.parse_args()

    if args.num_workers < 1:
        raise SystemExit("--num-workers must be at least 1")

    if args.num_workers == 1:
        _work(args.queue)
        return

    processes = [
        Process(target=_work, args=(args.queue,), name=f"rq-{args.queue}-{idx + 1}")
        for idx in range(args.num_workers)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join()


if __name__ == "__main__":
    main()
