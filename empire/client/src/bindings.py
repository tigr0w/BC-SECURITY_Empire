from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings

from empire.client.src.MenuState import menu_state

bindings = KeyBindings()


@Condition
def ctrl_c_filter():
    return bool(menu_state.current_menu_name in ("ShellMenu"))


@bindings.add("c-c", filter=ctrl_c_filter)
def do_ctrl_c(event):
    """
    If ctrl-c is pressed from the chat or shell menus, go back a menu.
    """
    menu_state.pop()
