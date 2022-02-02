"""

Common terminal messages used across Empire.

Titles, agent displays, listener displays, etc.

"""
from __future__ import print_function
from __future__ import absolute_import

from builtins import str
from builtins import range
import os
import time
import textwrap

# Empire imports
from . import helpers


def wrap_string(data, width=40, indent=32, indentAll=False, followingHeader=None):
    """
    Print a option description message in a nicely
    wrapped and formatted paragraph.

    followingHeader -> text that also goes on the first line
    """

    data = str(data)

    if len(data) > width:
        lines = textwrap.wrap(textwrap.dedent(data).strip(), width=width)

        if indentAll:
            returnString = ' ' * indent + lines[0]
            if followingHeader:
                returnString += " " + followingHeader
        else:
            returnString = lines[0]
            if followingHeader:
                returnString += " " + followingHeader
        i = 1
        while i < len(lines):
            returnString += "\n" + ' ' * indent + (lines[i]).strip()
            i += 1
        return returnString
    else:
        return data.strip()


def display_agent(agent, returnAsString=False):
    """
    Display an agent all nice-like.
    Takes in the tuple of the raw agent database results.
    """

    if returnAsString:
        agentString = "\n[*] Agent info:\n"
        for key, value in agent.items():
            if key != 'functions' and key != 'takings' and key != 'results':
                agentString += "  %s\t%s\n" % ('{0: <16}'.format(key), wrap_string(value, width=70))
        return agentString + '\n'
    else:
        print(helpers.color("\n[*] Agent info:\n"))
        for key, value in agent.items():
            if key != 'functions' and key != 'takings' and key != 'results':
                print("\t%s\t%s" % (helpers.color('{0: <16}'.format(key), "blue"), wrap_string(value, width=70)))
        print('')
