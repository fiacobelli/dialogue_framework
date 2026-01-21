import logging
from strings import MSG, BCKCHANSTR, BELSTR
import random

class DialogueManager:
    def __init__(self):
        self.logger = logging.getLogger('__main__.' + __class__.__name__)

    def setup(self,info_state, rule_mgr, goal_mgr):
        self.info_state =info_state
        self.rule_mgr  = rule_mgr
        self.goal_mgr = goal_mgr

    def dialogue(self, speech_interface, nlu, nlg, msg):
        self.logger.debug(f'{msg=}')
        while not self.is_dialogue_done():
            # listen
            msg[MSG.POSSIBLE_RESPONSES] = speech_interface.listen()
            check_passed = nlu.check(msg)
            if check_passed:
                self.manage(msg)
            else:
                msg[MSG.PROMPT] = self.get_backchannel_prompt()
            speech_interface.speak(nlg.get_prompt(msg))    
        self.prepare_exit(speech_interface, nlu, nlg, msg)
        return msg

    def is_dialogue_done(self):
        return self.info_state.bel.query(BELSTR.DONE)

    def intro(self, nlg, msg):
        self.manage(msg)
        msg[MSG.PROMPT] = nlg.get_opening_prompt() + msg[MSG.PROMPT]
        return True

    def manage(self, msg):
        self.logger.debug(f'{msg=}')
        self.rule_mgr.check_rules(self.info_state, msg)
        self.goal_mgr.update(msg,self.info_state)

    def get_backchannel_prompt(self):
        return random.choice(BCKCHANSTR.DM_BACKCHANNEL_PROMPTS)
 
    def prepare_exit(self, speech_interface, nlu, nlg, msg):
        self.logger.info("DIALOGUE IS FINISHING. SAVING USER")
        self.info_state.save_user_model()
        nlg.prep_closing_message(msg)

    def __str__(self) -> str:
        return self.__class__.__name__



