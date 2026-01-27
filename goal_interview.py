from goal import Goal
from strings import MSG, BELSTR

PHASE_PROMPTS = {
    'BEFORE': "Tell me about yourself - what was your life like before kidney disease?",
    'DURING': "How has dialysis changed your daily life?",
    'HOPE': "What would receiving a kidney transplant mean for you and your family?",
    'PHOTOS': "Thank you for sharing your story. Now let's add some photos to your page.",
    'COMPLETE': "Your microsite is ready to generate!",
}

# Localized phase prompts for non-English languages
PHASE_PROMPTS_ES = {
    'BEFORE': "Cuéntame sobre ti - ¿cómo era tu vida antes de la enfermedad renal?",
    'DURING': "¿Cómo ha cambiado la diálisis tu vida diaria?",
    'HOPE': "¿Qué significaría recibir un trasplante de riñón para ti y tu familia?",
    'PHOTOS': "Gracias por compartir tu historia. Ahora agreguemos algunas fotos a tu página.",
    'COMPLETE': "¡Tu sitio está listo para generar!",
}

PHASE_PROMPTS_AR = {
    'BEFORE': "أخبرني عن نفسك - كيف كانت حياتك قبل مرض الكلى؟",
    'DURING': "كيف غيّر غسيل الكلى حياتك اليومية؟",
    'HOPE': "ماذا سيعني حصولك على زراعة كلى لك ولعائلتك؟",
    'PHOTOS': "شكراً لمشاركة قصتك. الآن دعنا نضيف بعض الصور إلى صفحتك.",
    'COMPLETE': "موقعك جاهز للإنشاء!",
}

LANGUAGE_NAMES = {'en': 'English', 'es': 'Spanish', 'ar': 'Arabic'}

def get_phase_prompt(phase: str, lang: str = 'en') -> str:
    if lang == 'es':
        return PHASE_PROMPTS_ES.get(phase, PHASE_PROMPTS[phase])
    elif lang == 'ar':
        return PHASE_PROMPTS_AR.get(phase, PHASE_PROMPTS[phase])
    return PHASE_PROMPTS[phase]

PHASES = list(PHASE_PROMPTS.keys())


class InterviewGoal(Goal):
    def __init__(self, llm_provider, system_prompt: str):
        self.llm = llm_provider
        self.system_prompt = system_prompt

    def is_complete(self, info_state) -> bool:
        return (info_state.user.query('interview_phase') or 'BEFORE') == 'COMPLETE'

    def _get_responses(self, info_state, phase: str) -> list:
        return info_state.user.query(f'interview_{phase.lower()}') or []

    def _should_advance(self, info_state, phase: str) -> bool:
        responses = self._get_responses(info_state, phase)
        total_words = sum(len(r.split()) for r in responses)
        return len(responses) >= 2 and total_words >= 30

    def execute_goal(self, msg, info_state):
        history = info_state.user.query('conversation_history') or []
        user_input = msg.get(MSG.ORIG_TEXT, '')
        phase = info_state.user.query('interview_phase') or 'BEFORE'
        language = info_state.user.query('language') or 'en'

        # Store user response
        if user_input and phase in ['BEFORE', 'DURING', 'HOPE']:
            key = f'interview_{phase.lower()}'
            responses = self._get_responses(info_state, phase)
            responses.append(user_input)
            info_state.user.update(key, responses)
            history.append({"role": "user", "content": user_input})
            info_state.user.update('conversation_history', history)

        # Advance phase if ready
        if phase in ['BEFORE', 'DURING', 'HOPE'] and self._should_advance(info_state, phase):
            phase = PHASES[PHASES.index(phase) + 1]
            info_state.user.update('interview_phase', phase)

        # Generate response
        if phase in ['PHOTOS', 'COMPLETE']:
            response = get_phase_prompt(phase, language)
        else:
            phase_context = f"Current phase: {phase}. Topic: {PHASE_PROMPTS[phase]}"
            full_prompt = f"{self.system_prompt}\n\n{phase_context}"

            # Add language instruction for non-English
            if language != 'en':
                lang_name = LANGUAGE_NAMES.get(language, 'English')
                full_prompt += f"\n\nIMPORTANT: Respond entirely in {lang_name}. Be warm and culturally appropriate."

            response = self.llm.generate(history, full_prompt)

        history.append({"role": "assistant", "content": response})
        info_state.user.update('conversation_history', history)
        msg[MSG.RESPONSE] = response

    def get_next_prompt(self, msg, info_state) -> dict:
        msg[MSG.PROMPT] = msg.get(MSG.RESPONSE, PHASE_PROMPTS['BEFORE'])
        return msg


class InterviewGoalManager:
    def __init__(self, llm_provider, system_prompt: str):
        self.goal = InterviewGoal(llm_provider, system_prompt)

    def update(self, msg, info_state):
        if self.goal.is_complete(info_state):
            info_state.bel.add(BELSTR.DONE, True)
            return
        self.goal.execute_goal(msg, info_state)
        self.goal.get_next_prompt(msg, info_state)

    def get_opening(self, info_state, lang: str = 'en') -> str:
        phase = info_state.user.query('interview_phase') or 'BEFORE'
        if phase == 'BEFORE':
            greetings = {
                'en': "Hi! I'm here to help create your donor website. ",
                'es': "¡Hola! Estoy aquí para ayudarte a crear tu página de donante. ",
                'ar': "مرحباً! أنا هنا لمساعدتك في إنشاء صفحة التبرع الخاصة بك. "
            }
            return greetings.get(lang, greetings['en']) + get_phase_prompt('BEFORE', lang)
        return get_phase_prompt(phase, lang)
