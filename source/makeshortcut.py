# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com

시작 메뉴에 PyWinAgent 링크를 만든다. pythonw.exe 로 source/main.pyw 를 실행한다.
'''


import os
import sys

from shortcut import ShortCut
from utilities import APP_NAME


def get_pythonw():
    path = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    return path if os.path.exists(path) else sys.executable


def main():
    source = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(source)
    icon = os.path.join(root, 'assets', 'icon', 'icon.ico')

    path = ShortCut.get_user_programs_path(APP_NAME)
    ShortCut.create(
        path,
        target_path=get_pythonw(),
        arguments='"%s"' % os.path.join(source, 'main.pyw'),
        working_directory=source,
        icon=icon if os.path.exists(icon) else '')

    print('[ SHORTCUT CREATED ] [ {} ]'.format(path))


if __name__ == '__main__':
    main()
