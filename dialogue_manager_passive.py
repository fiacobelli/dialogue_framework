import logging
from strings import MSG, BCKCHANSTR, BELSTR
import random
from dialogue_manager import DialogueManager

class DialogueManagerPassive(DialogueManager):
    def __init__(self):
        self.logger = logging.getLogger('__main__.' + __class__.__name__)

    def setup(self,info_state, rule_mgr, goal_mgr):
        self.info_state =info_state
        self.rule_mgr  = rule_mgr
        self.goal_mgr = goal_mgr

    def dialogue(self, speech_interface, nlu, nlg, msg):
        '''
        This manages ONE turn of the dialogue manager. 
        Needs an initial message with MSG.POSSIBLE_RESPONSES set.
        
        :param self: Description
        :param speech_interface: Description
        :param nlu: Description
        :param nlg: Description
        :param msg: Description
        '''
        self.logger.debug(f'{msg=}')
        if not self.is_dialogue_done():
            # listen
            nlu.check(msg)
            self.manage(msg)
            nlg.get_prompt(msg)
        else: 
            self.prepare_exit(speech_interface, nlu, nlg, msg)
        return msg


