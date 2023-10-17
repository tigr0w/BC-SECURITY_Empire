import textwrap
import time

from prompt_toolkit import shortcuts


def color(string_name, color_name=None):
    """
    Change text color for the Linux terminal.
    """
    if not string_name:
        return ""
    string_name = str(string_name)

    attr = ["1"]
    # bold

    if color_name:
        if color_name.lower() == "red":
            attr.append("31")
        elif color_name.lower() == "green":
            attr.append("32")
        elif color_name.lower() == "yellow":
            attr.append("33")
        elif color_name.lower() == "blue":
            attr.append("34")

        if "\n" in string_name:
            str_list = string_name.split("\n")
            str_list_modified = []
            for s in str_list:
                str_list_modified.append("\x1b[{}m{}\x1b[0m".format(";".join(attr), s))
            return "\n".join(str_list_modified)
        else:
            return "\x1b[{}m{}\x1b[0m".format(";".join(attr), string_name)

    else:
        if string_name.strip().startswith("[!]"):
            attr.append("31")
            return "\x1b[{}m{}\x1b[0m".format(";".join(attr), string_name)
        elif string_name.strip().startswith("[+]"):
            attr.append("32")
            return "\x1b[{}m{}\x1b[0m".format(";".join(attr), string_name)
        elif string_name.strip().startswith("[*]"):
            attr.append("34")
            return "\x1b[{}m{}\x1b[0m".format(";".join(attr), string_name)
        elif string_name.strip().startswith("[>]"):
            attr.append("33")
            return "\x1b[{}m{}\x1b[0m".format(";".join(attr), string_name)
        else:
            return string_name


def title(version, server, modules, listeners, agents):
    """
    Print the tool title, with version.
    """
    shortcuts.clear()
    print(
        "========================================================================================"
    )
    print(" [\x1b[1;32mEmpire\x1b[0m] Post-Exploitation Framework")
    print(
        "========================================================================================"
    )
    print(
        " [\x1b[1;32mVersion\x1b[0m] %s | [Web] https://github.com/BC-SECURITY/Empire"
        % version
    )
    print(
        "========================================================================================"
    )
    print(
        " [\x1b[1;32mStarkiller\x1b[0m] Web UI | [Web] https://github.com/BC-SECURITY/Starkiller"
    )
    print(
        "========================================================================================"
    )
    print(
        " [\x1b[1;32mDocumentation\x1b[0m] | [Web] https://bc-security.gitbook.io/empire-wiki/"
    )
    print(
        "========================================================================================"
    )
    print(
        """
                   ███████╗███╗   ███╗██████╗ ██╗██████╗    ███████╗
                   ██╔════╝████╗ ████║██╔══██╗██║██╔══██╗   ██╔════╝
                   █████╗  ██╔████╔██║██████╔╝██║██████╔╝   █████╗
                   ██╔══╝  ██║╚██╔╝██║██╔═══╝ ██║██╔══██╗   ██╔══╝
                   ███████╗██║ ╚═╝ ██║██║     ██║██║  █████║███████╗
                   ╚══════╝╚═╝     ╚═╝╚═╝     ╚═╝╚═╝  ╚════╝╚══════╝

"""
    )
    print("              " + color(str(modules), "green") + " modules currently loaded")
    print("")
    print(
        "              "
        + color(str(listeners), "green")
        + " listeners currently active"
    )
    print("")
    print("              " + color(str(agents), "green") + " agents currently active")
    print("")
    print(color("Starkiller is now the recommended way to use Empire.", "green"))
    print(color(f"Try it out at {server}/index.html", "green"))


def loading():
    """
    Print and ascii loading screen.
    """

    print(
        """\x1b[1;1m
                                      `````````
                                 ``````.--::///+
                             ````-+sydmmmNNNNNNN
                           ``./ymmNNNNNNNNNNNNNN
                         ``-ymmNNNNNNNNNNNNNNNNN
                       ```ommmmNNNNNNNNNNNNNNNNN
                      ``.ydmNNNNNNNNNNNNNNNNNNNN
                     ```odmmNNNNNNNNNNNNNNNNNNNN
                    ```/hmmmNNNNNNNNNNNNNNNNMNNN
                   ````+hmmmNNNNNNNNNNNNNNNNNMMN
                  ````..ymmmNNNNNNNNNNNNNNNNNNNN
                  ````:.+so+//:---.......----::-
                 `````.`````````....----:///++++
                ``````.-/osy+////:::---...-dNNNN
                ````:sdyyydy`         ```:mNNNNM
               ````-hmmdhdmm:`      ``.+hNNNNNNM
               ```.odNNmdmmNNo````.:+yNNNNNNNNNN
               ```-sNNNmdh/dNNhhdNNNNNNNNNNNNNNN
               ```-hNNNmNo::mNNNNNNNNNNNNNNNNNNN
               ```-hNNmdNo--/dNNNNNNNNNNNNNNNNNN
              ````:dNmmdmd-:+NNNNNNNNNNNNNNNNNNm
              ```/hNNmmddmd+mNNNNNNNNNNNNNNds++o
             ``/dNNNNNmmmmmmmNNNNNNNNNNNmdoosydd
             `sNNNNdyydNNNNmmmmmmNNNNNmyoymNNNNN
             :NNmmmdso++dNNNNmmNNNNNdhymNNNNNNNN
             -NmdmmNNdsyohNNNNmmNNNNNNNNNNNNNNNN
             `sdhmmNNNNdyhdNNNNNNNNNNNNNNNNNNNNN
               /yhmNNmmNNNNNNNNNNNNNNNNNNNNNNmhh
                `+yhmmNNNNNNNNNNNNNNNNNNNNNNmh+:
                  `./dmmmmNNNNNNNNNNNNNNNNmmd.
                    `ommmmmNNNNNNNmNmNNNNmmd:
                     :dmmmmNNNNNmh../oyhhhy:
                     `sdmmmmNNNmmh/++-.+oh.
                      `/dmmmmmmmmdo-:/ossd:
                        `/ohhdmmmmmmdddddmh/
                           `-/osyhdddddhyo:
                                ``.----.`
                        \x1b[0m

          ███████╗███╗   ███╗██████╗ ██╗██████╗    ███████╗
          ██╔════╝████╗ ████║██╔══██╗██║██╔══██╗   ██╔════╝
          █████╗  ██╔████╔██║██████╔╝██║██████╔╝   █████╗
          ██╔══╝  ██║╚██╔╝██║██╔═══╝ ██║██╔══██╗   ██╔══╝
          ███████╗██║ ╚═╝ ██║██║     ██║██║  █████║███████╗
          ╚══════╝╚═╝     ╚═╝╚═╝     ╚═╝╚═╝  ╚════╝╚══════╝
                        """
    )

    time.sleep(3)
    shortcuts.clear()


def text_wrap(text, width=35):
    """
    Wraps text to newlines given a maximum width per line.
    :param text:
    :param width:
    :return: String wrapped by newlines at the given width
    """
    return "\n".join(textwrap.wrap(str(text), width=width))


def truncate(text, width=50):
    """
    Truncates text to the provided width. Adds a '..' at the end if truncated.
    :param text:
    :param width:
    :return: truncated text if necessary else the same text
    """
    return (text[:width] + "..") if len(text) > width else text


def connect_message():
    print("\n")
    print("Use the 'connect' command to connect to your Empire server.")
    print(
        "'connect -c localhost' will connect to a local empire instance with all the defaults"
    )
    print("including the default username and password.")
