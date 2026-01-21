from copyreg import pickle
import json
from strings import KBSTR, BELSTR, SPTEXTSTR # external strings
import pickle
import logging

class InformationState:
    def __init__(self, usermodelfile,kb_file):
        self.logger = logging.getLogger('__main__.' + __class__.__name__)
        self.kb = {}
        self.special_texts = {}
        self.load_knowledge_base(kb_file)
        self.bel = Belief()
        self.user_filename = usermodelfile
        self.user = UserModel.load(usermodelfile, self.logger)
        self.user.logging=self.logger
        self.cg = CommonGround()

    def __str__(self):
        return 'BELIEFS: ' + str(self.bel) + '\nCOMMON GROUND: ' + str(self.cg) + '\nUSER: ' + str(self.user)

    def load_knowledge_base(self, filename: str) -> None:
        self.logger.debug(f'{filename=}')
        with open(filename, 'r', encoding='utf-8') as f:
            file_contents = json.load(f)
            self.special_texts = file_contents[SPTEXTSTR.CUSTOM_MESSAGES]
            self.kb = file_contents[KBSTR.UNITS]    

    def save_user_model(self):
        self.logger.debug(f"Profile saved to {self.user_filename}")
        self.user.save(self.user_filename)

class Belief:

    """ Belief contains assumptions about intent, feeling, status, etc. 
        Beliefs are stored as key, value pairs. Value can be any primitive type or dictionary or list.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger('__main__.' + __class__.__name__)
        self.beliefs = {}

    def add(self, key, value):
        self.logger.debug(f'{key = }, {value = }')
        self.beliefs[key] = value  

    def remove(self, key):
        self.logger.debug(f'{key = }')
        self.beliefs.pop(key)    

    def query(self, key):
        self.logger.debug(f'{key = },  {self.beliefs.get(key) = }')
        if key in self.beliefs:
            return self.beliefs[key]
        else:
            return None  

    def update(self, key, value):
        self.logger.debug(f'{key = }, {value = }')
        self.beliefs[key] = value
    
    def __str__(self) -> str:
        return str(self.beliefs)

class CommonGround(Belief):
    """ Common ground contains established knowledge - must have an associated fact."""

    def __init__(self):
        """ Current functionality:  Creates empty dictionary. """
        self.logger = logging.getLogger('__main__.' + __class__.__name__)
        super().__init__()

    def __str__(self) -> str:
        return super().__str__()

class UserModel(Belief):

    def __init__(self) -> None:
        super().__init__()
        self.beliefs={BELSTR.MASTERY:{}}
        
    def add_mastery(self,key,val):
        self.logger.debug(f'{key = }, {val  = }')
        self.beliefs[BELSTR.MASTERY][key]=val

    def save(self, filename):
        self.logger.debug(f'{filename = }')
        with open(filename,"wb") as f:
            pickle.dump(self,f)

    @classmethod
    def load(cls,filename, logger):
        try:
             with open(filename,"rb") as f:
                return pickle.load(f)
        except FileNotFoundError:
            logger.debug("User File Not Found")
            return UserModel()
        except:
            logger.debug("Something went wrong opening user profile")
            return UserModel()

    def __str__(self) -> str:
        return super().__str__()
        
