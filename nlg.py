from strings import MSG, SPTEXTSTR
import logging

class NLG:
    def __init__(self):
        self.logger = logging.getLogger('__main__.' + __class__.__name__)
        self.opening_prompt: str = ''
        self.complete_program_prompt: str = 'bye.'
        self.end_session_prompt: str = ''

    def setup(self, special_texts : dict):
        self.opening_prompt = special_texts[SPTEXTSTR.INTRODUCTION_TEXT] + ".   "
        self.complete_program_prompt = '\n' + special_texts[SPTEXTSTR.COMPLETION_TEXT]
        self.end_session_prompt = '\n' + special_texts[SPTEXTSTR.END_SESSION_TEXT] # todo: not currently being used

    def get_prompt(self, msg : dict):
        self.logger.debug(f'PARAMETERS IN: {msg=}')
        if MSG.INTRO in msg:
            msg[MSG.PROMPT] = msg[MSG.INTRO]
        return msg[MSG.PROMPT]

    def get_opening_prompt(self):
        return self.opening_prompt

    def prep_closing_message(self, msg: dict) -> None:
        self.logger.debug(f'PARAMETERS IN: {msg=}')
        msg[MSG.PROMPT] = self.complete_program_prompt
