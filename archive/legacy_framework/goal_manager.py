from goal_bc import ContentGoal
from strings import MSG, BELSTR, KBSTR
import logging
import traceback

class GoalManager:
    def __init__(self, info_state, model_filename):
        self.logger = logging.getLogger('__main__.' + __class__.__name__)
        # should dialogue_application.py be calling the setup method instead?
        self.setup(info_state, model_filename)
        
    def setup(self, info_state, model_fname):
        mastered_elements = info_state.user.query(BELSTR.MASTERY)
        goal_objects = []
        for unit in info_state.kb:
            for topic in unit[KBSTR.TOPICS]:
                tkey = (unit[KBSTR.UNIT_ID], topic[KBSTR.TOPIC_ID])
                if tkey not in mastered_elements:
                    goal_objects += [ContentGoal(topic, tkey, info_state, model_fname)]
        info_state.bel.add(BELSTR.GOAL_OBJS, goal_objects)
        info_state.bel.add(BELSTR.PARA_ASKED, (0, 0, 0))
        info_state.bel.add(BELSTR.DONE, False)
        info_state.bel.add(BELSTR.IS_SYSPROMPT_SPECIAL, True)

    '''
        Checks what has been learned against all goals (units) and
        updates the goals list to only those goals that are not done yet.
        Returns the list of goals not completed
    '''      
    def check_all_goals(self,msg,info_state, goal_objs):
        for g in goal_objs:
            try:
                g.execute_goal(msg, info_state)
            except KeyError:
                trace = traceback.format_exc()
                self.logger.warning(f'KeyError! {g.id=} could not be executed\n{trace}\n')
        return [g for g in goal_objs if not g.is_complete(info_state)]
        
    def update(self, msg: dict, info_state):
        goals = info_state.bel.query(BELSTR.GOAL_OBJS)
        incomplete_goals = self.check_all_goals(msg,info_state, goals)
        info_state.bel.update(BELSTR.GOAL_OBJS, incomplete_goals) 
        if incomplete_goals:
            msg = incomplete_goals[0].get_next_prompt(msg,info_state) 
        else:
            info_state.bel.update(BELSTR.DONE, True)
            msg[MSG.PROMPT] = MSG.FAREWELL

