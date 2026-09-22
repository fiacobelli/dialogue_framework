"""Static configuration for the donor-story interview flow."""

INTERVIEW_STEPS: list[dict[str, object]] = [
    {
        'id': 'personal_background',
        'phase': 'STORY',
        'question': 'Can you tell me a little about yourself and the roles or relationships that matter most in your life?',
        'focus': 'who the patient is as a person, including family, work, community, hobbies, values, or identity',
        'required': 'one concrete identity detail such as family role, work, community, hobby, value, or place',
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
        'required': 'a concrete daily-life impact such as schedule, fatigue, activity limits, emotions, work, family, or independence',
        'allow_follow_up': True,
    },
    {
        'id': 'transplant_hope',
        'phase': 'STORY',
        'question': 'How would receiving a kidney transplant change your life?',
        'focus': 'specific hopes, activities, family moments, work, travel, energy, or independence',
        'required': 'a concrete life change, future goal, family moment, work, travel, activity, energy, or independence',
        'allow_follow_up': True,
    },
    {
        'id': 'donor_message',
        'phase': 'STORY',
        'question': 'What would you want a potential donor to know about you as a person?',
        'focus': 'a direct message to potential donors and what makes the story personal',
        'required': 'a direct message, personal value, reason to consider donation, or explicit request for help',
        'allow_follow_up': True,
    },
    {
        'id': 'support_network',
        'phase': 'STORY',
        'question': 'Do you have family, friends, or a community supporting you through this?',
        'focus': 'support network, community ties, and people who may be part of the story',
        'required': 'support people, support community, or an explicit statement that support is limited',
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

FOLLOWUP_EXAMPLES = {
    'personal_background': (
        'Could you tell me a little more, such as what you do, who matters most to you, or a hobby you enjoy?'
    ),
    'daily_life': (
        'Could you give me an example, such as feeling tired, missing an activity, or planning your day around dialysis?'
    ),
    'transplant_hope': (
        'What would you be able to do, such as having more energy, returning to work, enjoying a hobby, or spending time with family?'
    ),
    'donor_message': (
        'Could you share an example of a value, family story, or reason this help would matter to you?'
    ),
    'support_network': (
        'Who is there for you, such as a spouse, children, friends, a church, or a community group?'
    ),
}

# Use one follow-up by default; allow one final clarification when it is still useful.
MAX_FOLLOWUPS_PER_SECTION = 2

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
