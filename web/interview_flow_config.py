"""Static configuration for the donor-story interview flow."""

INTERVIEW_STEPS: list[dict[str, str]] = [
    {
        'id': 'personal_background',
        'phase': 'STORY',
        'question': 'Can you tell me a little about yourself and the roles or relationships that matter most in your life?',
        'focus': 'who the patient is as a person, including family, work, community, hobbies, values, or identity',
        'required': 'one concrete identity detail such as family role, work, community, hobby, value, or place',
    },
    {
        'id': 'medical_history',
        'phase': 'STORY',
        'question': 'When were you first diagnosed with kidney disease or kidney failure?',
        'focus': 'the beginning of the kidney disease journey',
        'required': 'diagnosis timing, dialysis timing, diagnosis context, or explicit uncertainty',
    },
    {
        'id': 'daily_life',
        'phase': 'STORY',
        'question': 'How has kidney failure affected your daily life, physically or emotionally?',
        'focus': 'dialysis, symptoms, daily limits, emotional burden, and what has changed',
        'required': 'a concrete daily-life impact such as schedule, fatigue, activity limits, emotions, work, family, or independence',
    },
    {
        'id': 'transplant_hope',
        'phase': 'STORY',
        'question': 'How would receiving a kidney transplant change your life?',
        'focus': 'specific hopes, activities, family moments, work, travel, energy, or independence',
        'required': 'a concrete life change, future goal, family moment, work, travel, activity, energy, or independence',
    },
    {
        'id': 'donor_message',
        'phase': 'STORY',
        'question': 'What would you want a potential donor to know about you as a person?',
        'focus': 'a direct message to potential donors and what makes the story personal',
        'required': 'a direct message, personal value, reason to consider donation, or explicit request for help',
    },
    {
        'id': 'support_network',
        'phase': 'STORY',
        'question': 'Do you have family, friends, or a community supporting you through this?',
        'focus': 'support network, community ties, and people who may be part of the story',
        'required': 'support people, support community, or an explicit statement that support is limited',
    },
    {
        'id': 'final_details',
        'phase': 'FINAL_DETAILS',
        'question': 'Is there anything else about your story, or any further details on something in particular, that you would like included?',
        'focus': 'final details, tone, quotes, photos, or personal stories before photo upload',
        'required': 'a final addition, tone preference, quote, story, or explicit nothing else',
    },
]

PROGRESS_LABELS = {
    'INTRO': 'Getting started',
    'WELCOME': 'Getting started',
    'STORY': 'Story interview',
    'FINAL_DETAILS': 'Final story details',
    'PHOTOS': 'Adding photos',
    'COMPLETE': 'Review and publish',
}

FINAL_PHOTOS_PROMPT = (
    "Thank you for sharing your story with me. "
    "The story part is complete, and the next step is to add up to three photos that you may want on your donor page."
)

SHORT_ANSWERS = {
    'yes', 'yeah', 'yep', 'yup', 'yea',
    'no', 'nah', 'nope',
    'ok', 'okay', 'alright', 'all right',
    'sure', 'fine', 'good', 'not really', 'none',
}

NO_RESPONSE_SENTINEL = '[no speech detected]'

ACKNOWLEDGEMENT_ONLY = {
    'yes', 'yeah', 'yep', 'yup', 'yea',
    'ok', 'okay', 'alright', 'all right', 'sure',
    'fine', 'good', 'right', 'correct',
}

CLARIFICATION_REQUESTS = {
    'what', 'huh', 'sorry', 'repeat', 'repeat that', 'say that again',
    'can you repeat', 'could you repeat', 'what do you mean',
}

OPERATIONAL_ISSUE_TERMS = {
    'clunky', 'frustrating', 'super frustrating', 'microphone', 'mic',
    'not picking', 'picking stuff up', 'pick stuff up', 'not hearing',
    "didn't hear", 'did not hear', 'speak louder', 'repeat what you said',
    'try again', 'cutting me off', 'cuts me off', 'not responsive',
    'taking a while', 'too slow', 'slower', 'hear me',
}

SKIP_TERMS = {
    'skip',
    'skip this',
    'skip this question',
    'pass',
    'i pass',
    'next',
    'next question',
    'move on',
    'prefer not to answer',
    "i'd rather not answer",
    'rather not answer',
    'do not want to answer',
    "don't want to answer",
}

READY_TERMS = {'yes', 'yeah', 'yep', 'yup', 'ready', 'sure', 'ok', 'okay', 'start', 'begin', 'go ahead'}
NOT_READY_TERMS = {'no', 'not yet', 'not ready', 'wait', 'hold on', 'later', 'stop', 'pause'}
READINESS_QUESTION_TERMS = {'why', 'what for', 'what is this', 'how does this work', 'who will see', 'share'}

NAME_MARKERS = (
    r'my name is',
    r'i am',
    r"i'm",
    r'call me',
    r'name is',
)

REJECT_NAME_WORDS = {
    'hi', 'hello', 'hey', 'okay', 'ok', 'yes', 'no', 'ready', 'start', 'begin',
    'patient', 'name', 'is', 'me', 'my',
}

DETAIL_TERMS: dict[str, set[str]] = {
    'personal_background': {
        'mother', 'father', 'mom', 'dad', 'wife', 'husband', 'daughter', 'son',
        'sister', 'brother', 'family', 'friend', 'teacher', 'work', 'job',
        'church', 'community', 'chicago', 'hobby', 'music', 'cook', 'cooking',
        'school', 'grandkids', 'children', 'kids',
    },
    'medical_history': {
        'year', 'years', 'month', 'months', 'ago', 'diagnosed', 'dialysis',
        'kidney', 'failure', 'started', 'doctor', 'hospital',
    },
    'daily_life': {
        'dialysis', 'treatment', 'tired', 'fatigue', 'exhausted', 'drained', 'pain', 'work', 'walk',
        'drive', 'sleep', 'family', 'kids', 'children', 'cook', 'travel',
        'appointments', 'schedule', 'hours', 'week', 'emotionally', 'sad',
        'scared', 'independent', 'independence', 'activities',
    },
    'transplant_hope': {
        'energy', 'travel', 'work', 'family', 'kids', 'children', 'grandkids',
        'independent', 'independence', 'freedom', 'school', 'cook', 'walk',
        'drive', 'future', 'life', 'normal', 'healthy', 'hobbies',
    },
    'donor_message': {
        'know', 'person', 'family', 'help', 'chance', 'life', 'donor',
        'grateful', 'thank', 'hope', 'mother', 'father', 'kids', 'children',
    },
    'support_network': {
        'family', 'friend', 'friends', 'church', 'community', 'wife', 'husband',
        'mother', 'father', 'daughter', 'son', 'sister', 'brother', 'support',
        'help', 'drive', 'caregiver', 'alone',
    },
    'final_details': {
        'include', 'quote', 'photo', 'photos', 'story', 'message', 'tone',
        'nothing', 'none', 'no', 'everything', 'ready',
    },
}

SECTION_TRANSITIONS: dict[str, str] = {
    'personal_background': "Let's start with who you are as a person.",
    'medical_history': "Now I want to understand the beginning of your kidney journey.",
    'daily_life': "Next, let's talk about what day-to-day life has been like.",
    'transplant_hope': "Now let's talk about what a transplant could make possible for you.",
    'donor_message': "Next, let's focus on what you would want a potential donor to understand.",
    'support_network': "I also want to understand who has been walking through this with you.",
    'final_details': "Before we move to photos, let's make sure we have not missed anything important.",
}

FOLLOWUP_QUESTIONS: dict[str, str] = {
    'personal_background': 'Could you tell me a little more about who you are outside of your illness?',
    'medical_history': 'Could you share a little more about when this kidney journey started for you?',
    'daily_life': 'Could you tell me more about how kidney failure affects your normal day?',
    'transplant_hope': 'Could you say more about what a transplant would help you do or feel again?',
    'donor_message': 'Could you tell me more about what you would want a potential donor to understand about you?',
    'support_network': 'Could you tell me a little more about who supports you, or whether support has been limited?',
    'final_details': 'Could you tell me what else you would like included, or say that there is nothing else?',
}

DEEPENING_MAX_PER_STEP = 1

CONTENT_STOPWORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'been', 'but', 'by', 'can',
    'could', 'do', 'for', 'from', 'has', 'have', 'how', 'i', 'if', 'in',
    'is', 'it', 'me', 'my', 'of', 'or', 'that', 'the', 'this', 'to', 'want',
    'what', 'when', 'with', 'would', 'you', 'your',
}
