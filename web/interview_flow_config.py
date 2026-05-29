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
