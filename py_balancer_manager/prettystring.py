from __future__ import print_function


class ColorNotFoundError(Exception):
    def __init__(self, message):
        message = '{}\navailable colors: {}'.format(message, ','.join(PrettyString.colorMap.keys()))
        super(ColorNotFoundError, self).__init__(message)


class PrettyString(str):
    mode = 'console'
    validModes = ['text', 'console', 'html']
    colorMap = {
        'reset': {'console': '\033[0m', 'html': '</span>'},
        'bold': {'console': '\033[1m', 'html': '<span style="font-weight:bold">'},
        'black': {'console': '\033[30m', 'html': '<span style="color:black">'},
        'red': {'console': '\033[31m', 'html': '<span style="color:darkred">'},
        'green': {'console': '\033[32m', 'html': '<span style="color:green">'},
        'yellow': {'console': '\033[33m', 'html': '<span style="color:goldenrod">'},
        'blue': {'console': '\033[34m', 'html': '<span style="color:blue">'},
        'magenta': {'console': '\033[35m', 'html': '<span style="color:darkmagenta">'},
        'cyan': {'console': '\033[36m', 'html': '<span style="color:darkcyan">'},
        'white': {'console': '\033[37m', 'html': '<span style="color:white">'},
        'lightblack': {'console': '\033[90m', 'html': '<span style="color:grey">'},
        'lightred': {'console': '\033[91m', 'html': '<span style="color:red ">'},
        'lightgreen': {'console': '\033[92m', 'html': '<span style="color:lightgreen">'},
        'lightyellow': {'console': '\033[93m', 'html': '<span style="color:yellow">'},
        'lightblue': {'console': '\033[94m', 'html': '<span style="color:lightblue">'},
        'lightmagenta': {'console': '\033[95m', 'html': '<span style="color:magenta">'},
        'lightcyan': {'console': '\033[96m', 'html': '<span style="color:lightcyan">'}
    }

    @staticmethod
    def setMode(mode):
        if mode not in PrettyString.validModes:
            raise Exception('not a valid mode in PrettyString: {0}'.format(mode))
        PrettyString.mode = mode

    @staticmethod
    def getMode():
        return PrettyString.mode

    def ljust(self, width):
        padded = str(self.text()).ljust(width)
        pstring = PrettyString(padded, self.color)
        return str(pstring)

    def text(self):
        """
        Returns the PrettyString as a standard python string without coloration
        """
        return self + ''

    def __new__(cls, value, color=None):
        if color in PrettyString.colorMap or color is None:
            obj = str.__new__(cls, value)
            obj.color = color
            return obj
        else:
            raise ColorNotFoundError('color is not defined: {}'.forrmat(color))

    def __str__(self):
        try:
            return PrettyString.colorMap[self.color][PrettyString.mode] + self + PrettyString.colorMap['reset'][PrettyString.mode]
        except:
            return self.text()
