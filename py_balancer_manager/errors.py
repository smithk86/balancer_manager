class BalancerManagerError(Exception):
    pass


class TaskExceptions(Exception):
    def __init__(self, tasks):
        self.tasks = tasks
        super(TaskExceptions, self).__init__(self, f'exception(s) occured in a list of tasks (count={len(self.tasks)}')

    def __iter__(self):
        for task in self.tasks:
            yield task
