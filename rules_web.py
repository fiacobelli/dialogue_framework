from strings import MSG


class RuleManagerWeb:
    """No-op rule manager for web. Framework requires it but we don't need rules."""

    def setup(self):
        pass

    def check_rules(self, info_state, msg: dict) -> None:
        msg[MSG.UPDATES] = []
