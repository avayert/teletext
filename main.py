# NOTE: run this in `python -u` for unbuffered input.

import atexit
import fcntl
import itertools
import os
import select
import signal
import sys
import termios
import threading
import time
import tty


ALT_MODE = '\33[?1049'
CURSOR   = '\33[?25'
ENABLE   = 'h'
DISABLE  = 'l'

CLEAR_BEGIN  = '\33[0J'
CLEAR_END    = '\33[1J'
CLEAR_SCREEN = '\33[2J'

UP    = b'\33[A'
DOWN  = b'\33[B'
RIGHT = b'\33[C'
LEFT  = b'\33[D'

CTRL_UP    = b'\33[1;5A'
CTRL_DOWN  = b'\33[1;5B'
CTRL_RIGHT = b'\33[1;5C'
CTRL_LEFT  = b'\33[1;5D'

HOME = '\33[H'
END  = '\33[F'

PAGE_UP   = '\33[5~'
PAGE_DOWN = '\33[6~'

# heh, this is BEL
CTRL_G = '\x07'

c_lflags = 3
original_termios = None
original_fcntl = None


PAGE_CACHE = {}


OFFSET_LEFT = (40 - 22) // 2
OFFSET_TOP = (40 - 3) // 2


def move_cursor_to(*, x, y):
    output(f'\33[{x};{y}H')

def output(*text):
    sys.stdout.write(''.join(text))


def terminal_resized():
    pass


def initialize_terminal():
    # store original terminal attributes so we can restore them after we exit
    global original_termios
    original_termios = termios.tcgetattr(sys.stdout.fileno())

    # turns out there _is_ cfmakeraw, it's just in a completely different module for some reason!
    tty.setraw(sys.stdout.fileno(), when=termios.TCSANOW)

    # `atexit` does not run when exceptions are thrown, for example. Instead we need these.
    signal.signal(signal.SIGTERM, restore_terminal);
    signal.signal(signal.SIGINT, restore_terminal);

    # I think this is only ran on graceful exit, but what do I know.
    atexit.register(restore_terminal)

    output(ALT_MODE, ENABLE)
    output(CLEAR_SCREEN)
    output(CURSOR, DISABLE)

    move_cursor_to(x=0, y=0)


def restore_terminal():
    output(CLEAR_SCREEN)
    output(CURSOR, ENABLE)
    output(ALT_MODE, DISABLE)

    # `original_X` can't be none because this can't be invoked until `initialize_terminal` has ran
    termios.tcsetattr(sys.stdout.fileno(), termios.TCSANOW, original_termios)


def wait_until_input_available():
    # screw epoll
    # there is no `timeout` argument, so this will block until a key is pressed.
    select.select([sys.stdin], [], [])

def input_available():
    # This is similar to the previous function, except we set timeout to 0, meaning we are in poll mode.
    # `select` immediately returns, and gives us the output of the query.
    ready_to_read, _, _ = select.select([sys.stdin], [], [], 0)

    # The list is empty if there is nothing to be read, and if there is it's juts gonna be stdin
    return bool(ready_to_read)

def load_page(page):
    event = threading.Event()

    output(CLEAR_SCREEN)

    def do_request():
        # TODO: do the actual request, right now I'm just sleeping for austerity
        time.sleep(2)
        event.set()

    # TODO: draw a box and a spinner
    # move_cursor_to(x=OFFSET_LEFT, y=OFFSET_TOP)

    move_cursor_to(x=0, y=0)

    spinner = itertools.cycle(('⢀⠀', '⡀⠀', '⠄⠀', '⢂⠀', '⡂⠀', '⠅⠀', '⢃⠀', '⡃⠀', '⠍⠀', '⢋⠀', '⡋⠀', '⠍⠁', '⢋⠁', '⡋⠁', '⠍⠉', '⠋⠉', '⠋⠉', '⠉⠙', '⠉⠙', '⠉⠩', '⠈⢙', '⠈⡙', '⢈⠩', '⡀⢙', '⠄⡙', '⢂⠩', '⡂⢘', '⠅⡘', '⢃⠨', '⡃⢐', '⠍⡐', '⢋⠠', '⡋⢀', '⠍⡁', '⢋⠁', '⡋⠁', '⠍⠉', '⠋⠉', '⠋⠉', '⠉⠙', '⠉⠙', '⠉⠩', '⠈⢙', '⠈⡙', '⠈⠩', '⠀⢙', '⠀⡙', '⠀⠩', '⠀⢘', '⠀⡘', '⠀⠨', '⠀⢐', '⠀⡐', '⠀⠠', '⠀⢀', '⠀⡀'))

    threading.Thread(target=do_request).start()

    # this busy loops blows but I couldn't think of a better way to do it...
    while True:
        if event.is_set():
            break

        output(CLEAR_END)
        output(f'Loading page {page:03} {next(spinner)}\r')

        time.sleep(1 / 20)

    return page



def read_input():
    page = 0

    output(CLEAR_SCREEN)
    output(f'Current page is: {page}/10\r\n')
    output(f'Got command: N/A')
    move_cursor_to(x=0, y=0)

    while True:
        wait_until_input_available()

        # NOTE:
        # it is _absolutely fucking essential_ we use `os.read` instead of sys.stdin.read(1) here.
        #
        # I spent like 50 minutes trying to figure out this dumb bug where for some reason multi-character inputs, like
        # say any of the arrow keys were read in a funky fashion where ESC was read but the other 2 characters were
        # left in some buffer, and only left after the next keypress. I tried like 7 different methods of making `stdin`
        # unbuffered, everything from setting it to raw mode to fnctl's O_NONBLOCK and even fucking manually calling
        # `vsetbuf` to no avail. `sys.stdin` seems to be some dumb IO wrapper that doesn't actually respect any of that
        # at all and you can't actually do unbuffered reads on it (maybe accessing `.buffer` works but this did not
        # occur to me at the time and I'm not changing this if it works).
        #
        # I am genuinely curious why on earth `select` was not returning when there _clearly_ was data in the buffer,
        # since after the next keypress it worked fine. I am really upset about this and I really do want to hear the
        # explanation for it.

        command = b''
        while input_available():
            command += os.read(sys.stdin.fileno(), 1)

        if command == LEFT:
            page = load_page(max(0, page - 1))
        elif command == RIGHT:
            page = load_page(min(10, page + 1))

        elif command == CTRL_LEFT:
            page = load_page(0)
        elif command == CTRL_RIGHT:
            page = load_page(10)

        output(CLEAR_SCREEN)
        output(f'Current page is: {page}/10\r\n')
        output(f'Got command: {command!r}')
        move_cursor_to(x=0, y=0)


        # ESC or C-z
        if command in (b'\x1a', b'\x1b'):
            break


if __name__ == '__main__':
    initialize_terminal()
    read_input()
