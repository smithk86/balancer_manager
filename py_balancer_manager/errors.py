class BalancerManagerError(Exception):
    pass


class MultipleExceptions(Exception):
    def __init__(self, exceptions):
        self.exceptions = exceptions
        super(MultipleExceptions, self).__init__(self, f'exception count: {len(self.exceptions)}')

    def __iter__(self):
        for e in self.exceptions:
            yield e
