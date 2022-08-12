import itertools
import json
import re
import sys

with open('output.json') as f:
    data = json.load(f)

lines = data['teletext']['page']['subpage'][0]['content'][1]['line']
lines = [line.get('Text', ' ' * 40) for line in lines]

foreground = '\x1B[3{}m'.format
background = '\x1B[4{}m'.format

reset = lambda: sys.stdout.write(foreground(9) + background(9) + '\n')


# While for the most part teletext corresponds to ASCII pretty OK, there are
# a few spots where they differ. The YLE teletext API seems to send all alpha-
# mode characters in their proper form a priori, so I do not need a separate
# table for it. (or at least as far as I can tell...)
#
# As a side note, the English teletext uses ← instead of [ and  → instead of ]
# which I think is pretty neat. Since Finnish has umlauts, we have no such
# luxury and are stuck with using them for real characters.
#
# You can see the G0 blocks here:
# https://en.wikipedia.org/wiki/Teletext_character_set#G0
#
# When not in alpha mode, there is a completely different set of characters we
# have to use. You can see the table on wikipedia here:
#
# https://en.wikipedia.org/wiki/Teletext_character_set#Graphics_character_sets
#
# It contains the G1 block characters, which are now luckily part of unicode.
#
# NOTE: I chose to use regular space here instead of the non-breaking space,
# because I do not think there is a functional difference, and it makes these
# strings align better.
#
# For this specific use case I wish python had C-style /* */ comments, so I
# could leave better inline hinting
#
# Anyway it works pretty OK as a dict regardless...
#
# The way you index into this is you take the character you want to draw in
# graphics mode, e.g. `~` (0x7E, 126). You `divmod` it to get the column and
# index into the string, e.g. `divmod(0x7E) = (0x7, 0xE)`.

# Hope this renders for you! If not it looks pretty much the same as the table
# below, they're just connected instead.
GRAPHICS_CHARACTERS = {
    0x2: ' 🬀🬁🬂🬃🬄🬅🬆🬇🬈🬉🬊🬋🬌🬍🬎',
    0x3: '🬏🬐🬑🬒🬓▌🬔🬕🬖🬗🬘🬙🬚🬛🬜🬝',
    0x6: '🬞🬟🬠🬡🬢🬣🬤🬥🬦🬧▐🬨🬩🬪🬫🬬',
    0x7: '🬭🬮🬯🬰🬱🬲🬳🬴🬵🬶🬷🬸🬹🬺🬻█',
}

# However, there is also the separated graphics mode. It is exactly the same as
# the regular graphics mode, except there is a tiny outline for the characters,
# leading to it looking like distinct boxes. For all intents and purposes we can
# simply use the 2x3 braille characters for this purpose.

SEPARATED_GRAPHICS = {
    0x2: '⠀⠁⠈⠉⠂⠃⠊⠋⠐⠑⠘⠙⠒⠓⠚⠛',
    0x3: '⠄⠅⠌⠍⠆⠇⠎⠏⠔⠕⠜⠝⠖⠗⠞⠟',
    0x6: '⠠⠡⠨⠩⠢⠣⠪⠫⠰⠱⠸⠹⠲⠳⠺⠻',
    0x7: '⠤⠥⠬⠭⠦⠧⠮⠯⠴⠵⠼⠽⠶⠷⠾⠿',
}

available_colours = 'black red green yellow blue magenta cyan white'.title().split()
graphics_colours = [f'G{colour}' for colour in available_colours]

# despite claiming so, the `structured` type of data does not actually contain
# enough information to properly display pages. You cannot tell when to enter
# the separated graphics mode. Thus I am manually parsing the `all` strings here


# At the start of the program, set the colours to be right
sys.stdout.write(foreground(7) + background(0))

for line in lines:
    # FIXME: this is black
    colour = 0

    graphics_mode = False
    separated_mode = False

    # this allows us to consume characters one by one
    token_stream = iter(line)

    for token in token_stream:
        # if we read a formatting opening tag...
        if token == '{':
            # then read until the end
            tokens = itertools.takewhile('}'.__ne__, token_stream)
            # and turn it back into a string
            mode = ''.join(tokens)

            if mode in graphics_colours:
                graphics_mode = True
                mode = mode.removeprefix('G')
                # I'm not actually 100% sure this should carry over but it
                # doesn't seem to matter in practice.
                colour = available_colours.index(mode)
                sys.stdout.write(foreground(colour))

            elif mode in available_colours:
                graphics_mode = False

                # we store `colour` in case a `NB` command is invoked to change
                # the actual background colour too.
                colour = available_colours.index(mode)

                # it's fine if we write a redundant foreground colour change
                # here, since a new one will be issued after a background change
                # or during a new line.
                sys.stdout.write(foreground(colour))

            elif mode == 'NB':
                sys.stdout.write(background(colour))

            elif mode == 'SG':
                separated_mode = True

            elif mode == 'DH':
                # there is nothing I can do about double height text, unfortunately.
                # For VTTs, double heights seems to automatically imply double
                # width, which is already a dealbreaker.
                #
                # In addition to that, no terminal seems to support interspersing
                # double height in an otherwise regular line. Teletext demands
                # this and thus the situation is unworkable, short of me making
                # a custom font just for this.
                pass

            else:
                sys.stdout.write(foreground(9) + background(9) + '\n')
                print('Found unknown mode:', mode)
                sys.exit(0)

            # we are supposed to advance the cursor by one, AFAICT
            sys.stdout.write(' ')

        else:
            # we are not in a formatting block, write the character

            if graphics_mode:
                # if we're in graphics mode, just look up to the tables described earlier
                # in the program.
                column, offset = divmod(ord(token), 16)
                table = SEPARATED_GRAPHICS if separated_mode else GRAPHICS_CHARACTERS
                token = table[column][offset]

            sys.stdout.write(token)

    # reset formatting right, so it doesn't "leak" onto the next line in case
    # nothing is written afterwards. End with a newline.
    #
    # TODO: add mode to respect user preferences.
    # 39 and 49 are the implementation-defined 'default' colours.
    #
    # This resets to white text on black background since that's what teletext
    # displays as out of the box.
    sys.stdout.write(foreground(7) + background(0) + '\n')

sys.stdout.write(foreground(9) + background(9) + '\n')
