# encoding: utf-8


'''
author: Taehong Kim
email: peppy0510@hotmail.com
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
    script = os.path.join(source, 'main.pyw')

    path = ShortCut.get_user_programs_path(APP_NAME)
    ShortCut.create(
        path,
        target_path=get_pythonw(),
        arguments=f'"{script}"',
        working_directory=source,
        icon=icon if os.path.exists(icon) else '')

    print(f'[ SHORTCUT CREATED ] [ {path} ]')


if __name__ == '__main__':
    main()
