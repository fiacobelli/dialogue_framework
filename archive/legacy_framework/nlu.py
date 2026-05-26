from strings import MSG
from decouple import config
from speech.estimate_functions import MaximumLikelihoodEstimate
from language_models import utility
import logging

SENTENCE_THRESHOLD = 0.05

class NLU:
    def __init__(self, bypass_sentence_completion: str):
        self.logger = logging.getLogger('__main__.' + __class__.__name__)
        self.bypass_sentence_completion = bypass_sentence_completion == 'True'
        self.maximum_likelihood_estimate = MaximumLikelihoodEstimate()
        self.sentence = ''   

    def process_command_for_profile_loading(self, possible_responses: list) -> str:
        msg = {}
        self.process_input(possible_responses, msg)
        # parse out the first word of their response to use as username
        msg = msg[MSG.ORIG_TEXT_LOWER].split(' ')
        return msg[0]
       

    def check(self, msg: dict) -> None:
        self.logger.debug(f'PARAMETERS IN: {msg=}')
        self.sentence += self.choose_input_to_use(msg[MSG.POSSIBLE_RESPONSES]) + ' '
        if self.bypass_sentence_completion or self.is_likely_complete(self.sentence):
            self.logger.info('calling process method')
            logging.basicConfig(filename='sentenceDetection.log', format='%(asctime)s %(name)s %(funcName)s %(levelname)s: %(message)s',level=logging.DEBUG)
            # bypassing sentence detection or likely is a sentence
            self.process(self.sentence, msg)
            self.sentence = ''
            return True
        # not likely a sentence 
        self.logger.info('process method not called')   
        return False

    def is_likely_complete(self, sentence):
        self.logger.debug(f'PARAMETERS IN: {sentence=}')
        likeliness_complete, __ = self.maximum_likelihood_estimate.mle(sentence)
        self.logger.info(f'pause detected, checking likeliness complete sentence. threshold: {SENTENCE_THRESHOLD}, likeliness complete {likeliness_complete}')
        return likeliness_complete >= SENTENCE_THRESHOLD   

    def choose_input_to_use(self, possible_responses : list) -> str:
        self.logger.debug(f'PARAMETERS IN: {possible_responses=}')
        text = possible_responses[0][1]  # just pick the most likely response
        return text 

    def process(self, orig_text : str, msg : dict) -> None:
        self.logger.debug(f'PARAMETERS IN:{orig_text=}, {msg=}')
        msg.clear()
        msg[MSG.ORIG_TEXT] = orig_text
        msg[MSG.ORIG_TEXT_LOWER] = orig_text.lower()
        msg[MSG.TOKENS] = utility.word_tokenize(orig_text.lower())
        msg[MSG.TOKENS_STEMMED] = utility.stem_list(msg[MSG.TOKENS], self.logger)
        # TODO: some kind of actual processing, as needed by Marianela
        # TODO : What to do with things like contractions?

    def remove_stopwords(self, msg : dict, start_key : str, save_key : str) -> None:
        self.logger.debug(f'PARAMETERS IN: {msg=}, {start_key=}, {save_key=}')
        msg[save_key] = utility.remove_stopwords(msg[start_key])
