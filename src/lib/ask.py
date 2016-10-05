def ask(message):
    message = '{0} # '.format(message)

    try:
        return input(message)
    except KeyboardInterrupt:
        print()
        return None


def select(message, options):
    while True:
        print(message)
        for i, option in enumerate(options):
            print('{0}: {1}'.format(i, option))
        input_ = ask('please select an option')

        if input_ is None:
            return None

        try:
            index = int(input_)
            return index
        except ValueError:
            print('please enter an integer corresponding to your selection')
            print()
        except KeyboardInterrupt:
            print()
            return None


def prompt(message=None):
    if message:
        message = '{0} [press enter]'.format(message)
    else:
        message = '[press enter]'

    try:
        input(message)
        return True
    except KeyboardInterrupt:
        print()
        return False


def confirm(message=None):
    if not message:
        message = 'Continue?'

    try:
        user_input = input(message + ' (y/n) ~# ')
    except KeyboardInterrupt:
        print()
        return False

    return user_input.lower().strip().startswith('y')
