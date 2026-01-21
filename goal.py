from abc import ABC, abstractmethod, abstractproperty

class Goal(ABC): 
    @abstractmethod
    def is_complete(self):
        assert NotImplementedError()

    @abstractmethod
    def execute_goal(self, msg, info_state):
        assert NotImplementedError()
    
    @abstractmethod
    def get_next_prompt(self, msg, info_state):
        assert NotImplementedError()
