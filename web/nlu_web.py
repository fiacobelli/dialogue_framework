from strings import MSG

from .config import INTERVIEW_EVIDENCE_SHADOW
from .evidence_interpreter import EvidenceInterpreter
from .interview_flow import build_interview_state, current_step, normalize_state


class NLUWeb:
    """Simplified NLU for web/text chat."""

    def __init__(self, info_state=None, llm_provider=None):
        self.info_state = info_state
        self.llm_provider = llm_provider

    def check(self, msg: dict) -> bool:
        """Parse user input and populate message dict with tokens."""
        possible = msg.get(MSG.POSSIBLE_RESPONSES, [])
        if not possible:
            return False
        text = possible[0][1] if isinstance(possible[0], tuple) else possible[0]
        if not text.strip():
            return False
        msg[MSG.ORIG_TEXT] = text
        msg[MSG.ORIG_TEXT_LOWER] = text.lower()
        msg[MSG.TOKENS] = text.lower().split()
        msg['nlu_frame'] = {
            'schema_version': 1,
            'source': 'web_nlu',
            'raw_text': text,
            'normalized_text': msg[MSG.ORIG_TEXT_LOWER],
            'tokens': msg[MSG.TOKENS],
            'turn_meta': msg.get('turn_meta') or {},
        }
        self._attach_semantic_frame(msg, text)
        return True

    def _attach_semantic_frame(self, msg: dict, text: str) -> None:
        if not (INTERVIEW_EVIDENCE_SHADOW and self.info_state and self.llm_provider):
            return
        state = normalize_state(self.info_state.user.query('interview_state') or build_interview_state())
        if state.get('awaiting') not in {'name', 'readiness', 'main_answer', 'followup_answer'}:
            return
        frame = EvidenceInterpreter(self.llm_provider).interpret(
            text,
            current_step(state),
            state,
            msg.get('turn_meta') or {},
            self.info_state.user.query('conversation_history') or [],
        )
        msg['evidence_interpretation_shadow'] = frame
        turn_meta = dict(msg.get('turn_meta') or {})
        turn_meta['evidence_interpretation_shadow'] = frame
        msg['turn_meta'] = turn_meta
        msg['nlu_frame']['semantic'] = frame
