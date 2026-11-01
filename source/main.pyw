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


def run_helper():
    # the packaged exe is also the Claude Code hook and the speaker it starts
    flag = sys.argv[1] if len(sys.argv) > 1 else ''
    if flag not in ('--hook', '--speak'):
        return False
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    if flag == '--hook':
        import ttshook
        ttshook.main()
    else:
        import ttsspeak
        ttsspeak.main()
    return True


def main():
    if run_helper():
        return
    if not has_running_instance():
        launch()
    else:
        show_running_window('PyWinAgent')


if __name__ == '__main__':
    main()
