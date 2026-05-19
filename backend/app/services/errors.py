class ServiceError(Exception):
    """Base class for domain errors raised by services."""


class NotFound(ServiceError):
    pass


class ValidationFailed(ServiceError):
    pass


class Conflict(ServiceError):
    pass


class EnqueueFailed(ServiceError):
    pass
