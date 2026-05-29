"""Patient communication scenarios for the microsite stress harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UserTurn:
    text: str
    meta: dict[str, Any] = field(default_factory=dict)
    note: str = ''


@dataclass
class Scenario:
    name: str
    communication_style: str
    risk_focus: str
    turns: list[UserTurn]


SCENARIOS = [
    Scenario(
        name='short_answer_user',
        communication_style='Very brief, sometimes one-word responses.',
        risk_focus='Whether the agent over-repairs short but valid answers.',
        turns=[
            UserTurn('Sam Carter'),
            UserTurn('yes'),
            UserTurn('father'),
            UserTurn('I have two kids and I work as a driver.'),
            UserTurn('2021'),
            UserTurn('I was diagnosed in 2021 and started dialysis last year.'),
            UserTurn('tired'),
            UserTurn('Dialysis leaves me tired after treatment and I miss family activities.'),
            UserTurn('more energy'),
            UserTurn('A transplant would give me more energy to work and be with my children.'),
            UserTurn('I am a family man and I would be grateful for a chance.'),
            UserTurn('my sister and my church help me'),
            UserTurn('no thank you'),
        ],
    ),
    Scenario(
        name='over_explaining_user',
        communication_style='Long answers, tangents, repetition, multiple details at once.',
        risk_focus='Whether long answers are accepted without unnecessary follow-up.',
        turns=[
            UserTurn('Denise Williams'),
            UserTurn('yes I am ready'),
            UserTurn(
                'I am a grandmother, I used to cook for everyone after church, and I still try '
                'to be the person people call when they need encouragement. I repeat myself '
                'sometimes because this has been a long road.'
            ),
            UserTurn('It started around 2018 when my doctor said my kidneys were failing, and then dialysis became part of my week.'),
            UserTurn('Dialysis takes hours, makes me exhausted, and sometimes I cannot cook or help with the grandchildren the way I used to.'),
            UserTurn('A transplant would let me travel to see my family, cook again, and feel more independent.'),
            UserTurn('I would want a donor to know I love my family deeply and I am asking for a chance to keep showing up for them.'),
            UserTurn('My daughter, my church friends, and my neighbor all support me.'),
            UserTurn('Please keep the story warm and hopeful.'),
        ],
    ),
    Scenario(
        name='emotional_vulnerable_user',
        communication_style='Emotionally vulnerable, uncertain, sensitive language.',
        risk_focus='Whether emotional disclosure is accepted supportively without derailing the flow.',
        turns=[
            UserTurn('Angela Brooks'),
            UserTurn('I think so, yes'),
            UserTurn('I am a mother and honestly my kids are the main reason I keep going.'),
            UserTurn('I was diagnosed about four years ago. It was scary and I still feel overwhelmed sometimes.'),
            UserTurn('It has made me tired and sad because I cannot do simple things with my children after dialysis.'),
            UserTurn('A transplant would mean I could be present again, not just surviving from treatment to treatment.'),
            UserTurn('I want a donor to know I am scared, but I am also hopeful and trying for my children.'),
            UserTurn('My sister helps me a lot, but I still feel alone sometimes.'),
            UserTurn('No, that is enough.'),
        ],
    ),
    Scenario(
        name='pause_thinking_user',
        communication_style='Pauses, silence, then continues with useful answers.',
        risk_focus='Whether pause-like no-response turns cause premature repair.',
        turns=[
            UserTurn('Robert King'),
            UserTurn('yes'),
            UserTurn('[no speech detected]', {'no_response': True}, 'thinking pause'),
            UserTurn('I am a retired mechanic, and my grandchildren are the most important people in my life.'),
            UserTurn('[no speech detected]', {'no_response': True}, 'thinking pause'),
            UserTurn('I think it was 2020 when the kidney failure became serious and I started dialysis soon after.'),
            UserTurn('It slows everything down. I get tired, and I plan my whole week around treatment.'),
            UserTurn('It would let me visit my grandkids without worrying about dialysis every few days.'),
            UserTurn('I would want them to know I am still trying to live a full life.'),
            UserTurn('My daughter drives me, and my family checks on me.'),
            UserTurn('Nothing else.'),
        ],
    ),
    Scenario(
        name='answers_future_questions_early',
        communication_style='Gives a large chunk of the whole story early.',
        risk_focus='Whether the agent avoids asking for information already given early.',
        turns=[
            UserTurn('Patricia Lane'),
            UserTurn('yes'),
            UserTurn(
                'I am a mother, a choir member, and I started dialysis in 2019. It changed my '
                'daily life because I am exhausted after treatment. A transplant would let me '
                'travel and help with my grandchildren again. I would want a donor to know I am '
                'grateful and hoping for a second chance. My church and my daughter support me.'
            ),
            UserTurn('I already said I started dialysis in 2019.'),
            UserTurn('Like I mentioned, treatment makes me exhausted and limits my time with family.'),
            UserTurn('As I said, I want to travel and help with my grandchildren again.'),
            UserTurn('I already told you I am grateful and hoping for a second chance.'),
            UserTurn('My church and daughter support me, as I said.'),
            UserTurn('No, nothing else.'),
        ],
    ),
    Scenario(
        name='confused_user',
        communication_style='Misunderstands questions, asks for clarification, goes off-topic.',
        risk_focus='Whether clarification stays calm and does not advance incorrectly.',
        turns=[
            UserTurn('George Miller'),
            UserTurn('what is this for'),
            UserTurn('okay yes'),
            UserTurn('Do you mean my medical history?'),
            UserTurn('I am a veteran and I like fixing radios for people.'),
            UserTurn('I am not sure what year exactly, maybe 2022 when the doctor said my kidneys were failing.'),
            UserTurn('The bus was late yesterday.'),
            UserTurn('Daily life is hard because dialysis makes me tired and my schedule is controlled by appointments.'),
            UserTurn('A transplant would help me be independent and visit my brother.'),
            UserTurn('I want donors to know I try to help people when I can.'),
            UserTurn('My neighbor and brother support me.'),
            UserTurn('No thanks.'),
        ],
    ),
    Scenario(
        name='elderly_low_tech_user',
        communication_style='Simple phrasing, navigation uncertainty, slower wording.',
        risk_focus='Whether simple answers are treated respectfully and accepted when meaningful.',
        turns=[
            UserTurn('Mary Thompson'),
            UserTurn('yes dear'),
            UserTurn('I am a grandmother. I go to church and my family means everything.'),
            UserTurn('I do not remember the exact year, but the kidney doctor told me and then dialysis started.'),
            UserTurn('It makes me tired. I cannot stand long and I need help getting to treatment.'),
            UserTurn('A transplant would help me have strength and be around my grandchildren.'),
            UserTurn('Tell them I am thankful and I just want more time with my family.'),
            UserTurn('My daughter helps me with rides and medicine.'),
            UserTurn('No baby, that is all.'),
        ],
    ),
    Scenario(
        name='fast_informal_user',
        communication_style='Rapid, informal, jumps between ideas.',
        risk_focus='Whether informal wording is still recognized as evidence.',
        turns=[
            UserTurn('Marcus Reed'),
            UserTurn('yeah let us do it'),
            UserTurn('I am a dad, barber, music guy, always with my nephews and family.'),
            UserTurn('Kidneys went bad like 2020, dialysis came after that.'),
            UserTurn('It messes with everything, work, sleep, mood, all of it.'),
            UserTurn('Transplant means freedom, energy, back to cutting hair and moving around.'),
            UserTurn('A donor should know I am real, I care about people, and this would change my life.'),
            UserTurn('My mom, my girl, and my cousins got me.'),
            UserTurn('Nah I am good.'),
        ],
    ),
    Scenario(
        name='nonlinear_storyteller',
        communication_style='Events out of order, unstructured but meaningful.',
        risk_focus='Whether out-of-order storytelling is accepted without forcing rigid structure.',
        turns=[
            UserTurn('Linda Harris'),
            UserTurn('yes'),
            UserTurn('Before all this I was the person organizing family birthdays. These days dialysis is always in the middle of everything, but my family still sees me as the planner.'),
            UserTurn('I remember the hospital first, then later they explained kidney failure. I think diagnosis was around 2021.'),
            UserTurn('Some days I feel okay, then dialysis drains me and I cancel plans. Emotionally that is hard.'),
            UserTurn('I want the transplant so I can plan birthdays and travel without treatment controlling the calendar.'),
            UserTurn('I want a donor to know I am not just sick; I am a mother and friend with people counting on me.'),
            UserTurn('My sisters and my nieces support me.'),
            UserTurn('Please include that family gatherings matter to me.'),
        ],
    ),
    Scenario(
        name='mixed_difficult_case',
        communication_style='Emotion, rambling, clarification, pauses, partial answers.',
        risk_focus='Whether the system recovers without becoming repetitive or cold.',
        turns=[
            UserTurn('Evelyn Scott'),
            UserTurn('yes'),
            UserTurn('I do not know where to start. I guess I am a mother, I used to work at a school, and this whole thing has made me feel small.'),
            UserTurn('sorry can you repeat that'),
            UserTurn('It was maybe five years ago when the kidney issue became real and dialysis started later.'),
            UserTurn('[no speech detected]', {'no_response': True}, 'emotional pause'),
            UserTurn('Daily life is appointments, fatigue, and feeling like I am missing my family life.'),
            UserTurn('A transplant would mean I could breathe again, work part time, and be there for my son.'),
            UserTurn('I want a donor to know I am scared to ask, but this would give me a chance.'),
            UserTurn('My son and sister support me, but it is still hard.'),
            UserTurn('No, I think that covers it.'),
        ],
    ),
]


def _variant(base: Scenario, index: int) -> Scenario:
    turns = [UserTurn(t.text, dict(t.meta), t.note) for t in base.turns]
    turns[0].text = f"{turns[0].text} {index + 1}"
    readiness = ['yes', 'yes I am ready', 'okay yes', 'sure', 'yeah let us do it']
    if len(turns) > 1:
        turns[1].text = readiness[index % len(readiness)]
    final_phrases = ['nothing else', 'no thank you', 'that is enough', 'that covers it', 'nah i am good', 'no that is all']
    turns[-1].text = final_phrases[index % len(final_phrases)]
    if index % 5 == 4 and len(turns) > 4:
        turns.insert(3, UserTurn('[no speech detected]', {'no_response': True}, 'generated thinking pause'))
    return Scenario(
        name=f'{base.name}_v{index + 1:02d}',
        communication_style=base.communication_style,
        risk_focus=base.risk_focus,
        turns=turns,
    )


def expand_scenarios(variants_per_scenario: int) -> list[Scenario]:
    if variants_per_scenario <= 1:
        return SCENARIOS
    expanded = []
    for scenario in SCENARIOS:
        expanded.extend(_variant(scenario, index) for index in range(variants_per_scenario))
    return expanded
