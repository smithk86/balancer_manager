class BalancerManagerError(Exception):
    pass


class HttpdVersionError(BalancerManagerError):
    pass


class MultipleBalancerManagerErrors(BalancerManagerError):
    pass


class ResultsError(BalancerManagerError):
    pass


class ValidationClientError(BalancerManagerError):
    pass


class NotFound(ResultsError):
    pass
