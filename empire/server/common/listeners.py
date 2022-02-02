from builtins import object


class Listeners(object):
    """
    At this point, just a pass-through class to the v2 listener service
    until we get around to more refactoring.
    """

    def __init__(self, main_menu, args):

        self.mainMenu = main_menu
        self.args = args

    def is_listener_valid(self, name):
        return self.mainMenu.listenersv2.get_active_listener_by_name(name) is not None
