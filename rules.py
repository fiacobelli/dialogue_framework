from abc import ABC, abstractmethod
from goal_manager import GoalManager
from information_state import InformationState, Belief
from strings import MSG, BELSTR, RUSTR
import logging
import traceback



class RuleManager:
    def __init__(self):
        self.logger = logging.getLogger('__main__.' + __class__.__name__)

    def setup(self) -> None:
        self.rule_list = [SpecialRule(), UserExitRule(), GoalsCompleteRule(), UpdateAndContinueRule()]

    def check_rules(self, info_state, msg) -> list:
        self.logger.debug('Checking rules')
        # try/except for missing keys
        updates = []
        for rule in self.rule_list:
            try:
                result = rule.check(info_state, msg)
            except KeyError:
                trace = traceback.format_exc()
                self.logger.warning(f'key missing for rule check:\n{trace}\n')
                continue
            if result:
                updates.append(result)
        updates.sort(key=lambda t: t[0])
        msg[MSG.UPDATES] = updates


class Rule(ABC):
    @abstractmethod
    def check(self, info_state: InformationState, msg: dict):
        assert NotImplementedError()

class SpecialRule(Rule):
    def check(self, info_state: InformationState, msg: dict):
        self.logger = logging.getLogger('__main__.' + __class__.__name__)
        if info_state.bel.query('is_prompt_special') and MSG.QUIT not in msg[MSG.TOKENS]:
            return 'special_action'
        return None
        
class UserExitRule(Rule):
    def check(self, info_state, msg):
        self.logger = logging.getLogger('__main__.' + __class__.__name__)
        result = None
        if MSG.QUIT in msg[MSG.TOKENS]:
            info_state.bel.update(BELSTR.DONE, True)
            result = RUSTR.USER_EXIT
        self.logger.debug(f'* CHECKING DONE RULE - Status: {result}')
        return result

class GoalsCompleteRule(Rule):
    def check(self, info_state, msg):
        self.logger = logging.getLogger('__main__.' + __class__.__name__)
        result = None
        if not info_state.bel.query(BELSTR.GOAL_OBJS):
            info_state.bel.update(BELSTR.DONE, True)
            result = RUSTR.GOALS_COMPLETE   
        self.logger.debug(f'* CHECKING GOALS COMPLETE RULE - Status: {result}')
        return result
        
class UpdateAndContinueRule(Rule):
    def check(self, info_state, msg):
        self.logger = logging.getLogger('__main__.' + __class__.__name__)
        result = None
        if MSG.QUIT not in msg[MSG.TOKENS] and info_state.bel.query(BELSTR.GOAL_OBJS):
            info_state.bel.update(BELSTR.DONE, False)
            result = RUSTR.UPDATE_AND_CONTINUE
        self.logger.debug(f'* CHECKING UPDATE AND CONTINUE RULE - Status: {result}')
        return result


    