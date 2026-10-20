# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
'''


import sys

from wininstance import has_running_instance
from wininstance import show_running_window


class stderr:
    def write(self, *args, **kwargs):
        pass


if not sys.stderr:
    sys.stderr = stderr()


def launch():
    from mainapp import launch_mainapp
    launch_mainapp()


def main():
    if not has_running_instance():
        launch()
    else:
        show_running_window('PyWinAgent')


if __name__ == '__main__':
    main()
