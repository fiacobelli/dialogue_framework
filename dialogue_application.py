from decouple import config
from importlib import import_module
print(config('SPEECH_INTERFACE'))
NLU = import_module(config('NLU')).NLU
NLG = import_module(config('NLG')).NLG
SpeechInterface = import_module(config('SPEECH_INTERFACE')).SpeechInterface
DialogueManager = import_module(config('DIALOGUE_MANAGER')).DialogueManager
InformationState = import_module(config('INFORMATION_STATE')).InformationState
GoalManager = import_module(config('GOAL_MANAGER')).GoalManager
RuleManager = import_module(config('RULES_MANAGER')).RuleManager
import logging
import argparse

def main(userfile):
    speech_interface, nlu, nlg, dialogue_manager, info_state, rules, goal_mgr, logger = setup(userfile)
    dialogue_manager.setup(info_state, rules, goal_mgr)
    dialogue_manager.rule_mgr.setup()
    nlg.setup(dialogue_manager.info_state.special_texts)
    run(dialogue_manager, speech_interface, nlu, nlg)
    logger.debug(f"PROGRAM ENDED. USER FILE:{userfile}")

def setLogger():
    logger = logging.getLogger()
    logging.basicConfig(filename=config('TUTORING_LOG'), format='%(asctime)s %(name)s %(funcName)s %(levelname)s: %(message)s',level=logging.DEBUG)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    console_handler.setFormatter(logging.Formatter('%(name)s - %(levelname)s - %(funcName)s - %(message)s'))
    return logger

def setup(userfile):
    logger = setLogger()
    speech_interface = SpeechInterface(config('CLOUDSPEECH'))
    nlu = NLU(config('BYPASS_SENTENCE_COMPLETION'))
    nlg = NLG()
    dialogue_manager = DialogueManager()
    info_state = InformationState(userfile, config('TRAINING_FILE'))
    rules = RuleManager()
    goal_mgr = GoalManager(info_state, config('SIMILARITY_MODEL'))
    return speech_interface, nlu, nlg, dialogue_manager, info_state, rules, goal_mgr, logger

def run(dialogue_manager, speech_interface, nlu, nlg):
    msg = dict()
    dialogue_manager.intro(nlg, msg) 
    speech_interface.speak(nlg.get_prompt(msg))
    msg = dialogue_manager.dialogue(speech_interface, nlu, nlg, msg)
    speech_interface.speak(nlg.get_prompt(msg)) # this is the "closing remarks"

if __name__ == '__main__':
    parser = argparse.ArgumentParser("Start a Dialogue")
    parser.add_argument('-f','--file',nargs=1,default='user.log',type=ascii, help="specify the user model's filename")
    parser.add_argument('-c','--config',nargs = '*', default= None, type=ascii, help="specify configuration environment")
    args = parser.parse_args()
    main(args.file[0][1:-1])
