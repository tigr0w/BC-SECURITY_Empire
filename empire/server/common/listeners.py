import warnings


class Listeners:
    """
    At this point, just a pass-through class to the v2 listener service
    until we get around to more refactoring.
    """

    def __init__(self, main_menu, args):
        self.mainMenu = main_menu
        self.args = args

    def is_listener_valid(self, name):
        warnings.warn(
            "This has been deprecated and may be removed. Use listener_service.get_active_listener_by_name().",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.mainMenu.listenersv2.get_active_listener_by_name(name) is not None
