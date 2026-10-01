"""Static configuration for the donor-story interview flow."""

INTERVIEW_STEPS: list[dict[str, object]] = [
    {
        'id': 'personal_background',
        'phase': 'STORY',
        'question': 'Can you tell me about yourself and the roles or relationships that matter most in your life?',
        'focus': 'who the patient is as a person, including family, work, community, hobbies, values, or identity',
        'required': ('who or what matters most to them plus at least one specific thing about it, such as what a '
                     'family member is like, what they do or did for work, or what they enjoy; naming people or '
                     'roles alone is not enough'),
        'allow_follow_up': True,
    },
    {
        'id': 'medical_history',
        'phase': 'STORY',
        'question': 'When were you first diagnosed with kidney disease or kidney failure?',
        'focus': 'the beginning of the kidney disease journey',
        'required': 'diagnosis timing, dialysis timing, diagnosis context, or explicit uncertainty',
        'allow_follow_up': False,  # factual timeline anchor; a brief date is sufficient
    },
    {
        'id': 'daily_life',
        'phase': 'STORY',
        'question': 'How has kidney failure affected your daily life, physically or emotionally?',
        'focus': 'dialysis, symptoms, daily limits, emotional burden, and what has changed',
        'required': ('at least one specific example of how life has changed, such as what a dialysis day is like, '
                     'something they can no longer do, or how it feels; a general statement like "it is hard" '
                     'alone is not enough'),
        'allow_follow_up': True,
    },
    {
        'id': 'transplant_hope',
        'phase': 'STORY',
        'question': 'How would receiving a kidney transplant change your life?',
        'focus': 'specific hopes, activities, family moments, work, travel, energy, or independence',
        'required': ('at least one specific thing they would do or get back, with enough detail to picture it; '
                     '"spend more time" or "feel better" alone is not enough'),
        'allow_follow_up': True,
    },
    {
        'id': 'donor_message',
        'phase': 'STORY',
        'question': 'What would you want a potential donor to know about you as a person?',
        'focus': 'a direct message to potential donors and what makes the story personal',
        'required': ('something personal a donor could connect with, such as a value they live by with an example, '
                     'what they give to others, or why this help would matter; a general trait like "good person" '
                     'alone is not enough'),
        'allow_follow_up': True,
    },
    {
        'id': 'support_network',
        'phase': 'STORY',
        'question': 'Who, if anyone, is supporting you through this?',
        'focus': 'support network, community ties, and people who may be part of the story',
        'required': ('who supports them and at least one thing those people do or mean to them, or an explicit '
                     'statement that support is limited; naming people alone is not enough'),
        'allow_follow_up': True,
    },
    {
        'id': 'final_details',
        'phase': 'FINAL_DETAILS',
        'question': 'Is there anything else about your story, or any further details on something in particular, that you would like included?',
        'focus': 'final details, tone, quotes, photos, or personal stories before photo upload',
        'required': 'a final addition, tone preference, quote, story, or explicit nothing else',
        'allow_follow_up': False,  # terminal step; never probe
    },
]

# Fallback follow-up per section: spoken as-is when the model gives none, and never a repeat of
# the main question. Each gives two examples of what other people say, then asks the patient.
FOLLOWUP_EXAMPLES = {
    'personal_background': (
        'Some people talk about their work, and others about their family or a hobby they love. '
        'What would you want people to know about you?'
    ),
    'daily_life': (
        'Some people feel very tired after dialysis, and others have had to give up work or activities they enjoy. '
        'What has changed for you?'
    ),
    'transplant_hope': (
        'Some people look forward to more time with their family, and others to getting back to work or a hobby. '
        'What would you be able to do?'
    ),
    'donor_message': (
        'Some people are known for helping others, and some for how much they care for their family. '
        'What would the people close to you say about you?'
    ),
    'support_network': (
        'Some people have a spouse or children who help, and others lean on friends or a church. '
        'What do the people around you do to help?'
    ),
}

# One follow-up, then a second, easier one if the answer is still thin.
MAX_FOLLOWUPS_PER_SECTION = 2

# Exact (normalized) main answers that always get a follow-up, whatever the model decides.
VAGUE_ANSWERS = {
    'yes', 'yeah', 'yep', 'it is bad', "it's bad", 'it is hard', "it's hard",
    'it would be better', 'it will be better', "it'll be better", 'it would make it better',
    'it will make it better', "it'll make it better", 'i am a good person', "i'm a good person",
}

# A short answer matching one of these means the patient is unsure or declining: never probe.
DECLINE_MAX_WORDS = 8
DECLINE_PATTERNS = (
    r"\b(do not|don'?t|don t) know\b",
    r"\bnot sure\b",
    r"\brather not\b",
    r"\b(do not|don'?t|don t) want to (say|talk|answer|share)\b",
    r"\bnothing (else|more)\b",
    r"\b(that's|that s|that is) (it|all)\b",
    r"\bskip\b",
)
# As the whole reply to a follow-up question, these also mean "no more to add".
DECLINE_FOLLOWUP_REPLIES = {'no', 'nope', 'nah', 'no thanks', 'no thank you'}

GENERATION_REQUIRED_EVIDENCE_GROUPS = {
    'identity': ('personal_background',),
    'kidney_experience': ('medical_history', 'daily_life'),
    'hope': ('transplant_hope',),
    'donor_message': ('donor_message',),
}

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

NO_RESPONSE_SENTINEL = '[no speech detected]'
