# strings for msg dictionary
class MSG:
    FAREWELL = "Well done! good bye."
    INTRO = 'intro'
    LIKELY_IS_SENTENCE = 'likely_is_sentence'
    ORIG_TEXT = 'orig_text'
    ORIG_TEXT_LOWER = 'orig_text_lower'
    POSSIBLE_RESPONSES = 'possible_responses'
    PROMPT = 'prompt'
    QUIT = 'quit'
    RESPONSE = 'response'
    TOKENS = 'tokens' 
    TOKENS_STEMMED = 'tokens_stemmed'
    UPDATES = "updates"


# strings for rules
class RUSTR:
    GOALS_COMPLETE = 'goals_complete'
    SPECIAL_ACTION = 'special_action'
    USER_EXIT = 'user_exit'
    UPDATE_AND_CONTINUE = 'update_and_continue'
    

class BCKCHANSTR:
    # strings for dialogue manager
    DM_BACKCHANNEL_PROMPTS = ['would you like to say more', 'anything more to add', 'would you like to continue or is that it', 'is that all or do you care to continue', 'you can keep going if you like', 'would you like to add more', 'is there anything else', 'does that complete your response', 'did you want to expand on your response', 'is your response complete']
    # strings for goal_bc/content_goal
    GOAL_BACKCHANNEL_PROMPTS = ["uh-huh","ok","right","hmm","i see","got it"]
    NEW_GOAL_PROMPTS = ["here we go", "let's get started", "good", "alright", "thank you"]


# strings for custom messages/special texts
class SPTEXTSTR:
    COMPLETION_TEXT = 'completion_text'
    CUSTOM_MESSAGES = 'custom_messages'
    END_SESSION_TEXT = 'end_session_text'
    INTRODUCTION_TEXT = 'introduction_text'
    SPECIAL_TEXTS = 'special_texts'

# strings knowledge base/json content file
class KBSTR:
    ALT_QUESTION = 'alt_question'
    ALT_TEXT = 'alt_text'
    CATCHALL_PROMPT = "I can't think of anything else to say. Would you like to add something?"
    CONTENTS = 'contents'
    INTRO = 'intro'
    KB = 'kb'
    KEYWORDS = 'keywords'
    OUTRO='outro'
    PARAGRAPH_ID = 'paragraph_id'
    PARA_KEYS = 'para_keys'
    PKEY = 'pkey'
    QUESTION = 'question'
    TEXT = 'text'
    TOPIC_ID = 'topic_id'
    TOPIC_NAME = 'topic_name'
    TOPICS = 'topics'
    UNIT_ID = 'unit_id'
    UNIT_NAME = 'unit_name'
    UNITS = 'units'

# strings for beliefs
class BELSTR:
    COMPLETE = 'complete'
    CURRENT_GOAL = 'current_goal'
    DATA = 'data'
    DONE = 'done'
    GIVEN_ANSWER = 'given_answer'
    GOALS = 'goals'
    GOAL_ID = 'goal_id'
    GOAL_OBJS = 'goal_objs'
    GOAL_ID = 'goal_id'
    IS_CONTENT_COMPLETE = 'is_content_complete'
    IS_CURRENT_GOAL = 'is_current_goal'
    IS_INTRO_COMPLETE = 'is_intro_complete'
    IS_OUTRO_COMPLETE = 'is_outro_complete'
    IS_PENDING_SPECIAL_USERRESPONSE = 'is_pending_special_userresponse'
    IS_SYSPROMPT_SPECIAL = 'is_sysprompt_special'
    MASTERY = "mastery"
    MISSING_KEYWORDS = 'missing_keywords'
    NUM_REPS = 'num_reps'
    PARAGRAPH = 'paragraph'
    PARA_ASKED = 'para_asked'
    PKEY = 'pkey'
    PKEYS = 'pkeys'
    SHELF = 'shelf'
    SIMILARITY = 'similarity'
    TARGET_ANSWER = 'target_answer'
    TKEYS = 'tkeys'