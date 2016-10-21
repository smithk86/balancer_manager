class BalancerManagerError(Exception):
    pass


class ValidationClientError(BalancerManagerError):
    pass


class ResultsError(BalancerManagerError):
	pass


class NotFound(ResultsError):
    pass
