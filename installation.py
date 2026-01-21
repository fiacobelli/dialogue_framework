import os
import platform

def set_up_ubuntu():
    os.system('sudo apt install python3-pip')
    os.system('sudo apt install --user pipenv')
    os.system('sudo apt-get install libasound-dev')
    os.system('sudo apt-get install portaudio19-dev')
    os.system('sudo apt-get install portaudio2')
    os.system('sudo apt-get install portaudioccp0')
    os.system('sudo apt-get install espeak')
    os.system('pipenv run pip install -r requirements.txt')
    os.system('pipenv run pip install pyaudio')
    os.system('pipenv run python -m spacy download en_core_web_sm')
    os.system("export PYTHONPATH=${PYTHONPATH}:.")       


def set_up_windows():
    os.system("pip install --user pipenv")
    os.system('pipenv run pip install -r requirements.txt')
    os.system('pipenv run pip install pyaudio')
    os.system('pipenv run python -m spacy download en_core_web_sm')
    os.system("set PYTHONPATH=%PYTHONPATH;.")

def set_up_mac():
    os.system('python -m ensurepip')
    os.system('pip install --user pipenv')
    os.system('pipenv run pip install -U pyobjc')
    os.system('pipenv run pip install -r requirements.txt')
    os.system('pipenv run python -m spacy download en_core_web_sm')
    os.system("brew install portaudio --HEAD")
    os.system('pipenv run pip install pyaudio')
    os.system("export PYTHONPATH=${PYTHONPATH}:.")

def setup_env():
    with open('configuration/environment.py', 'r', encoding='utf-8') as f:
        contents = f.read()
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(contents)

def set_pythonpath(): 
    dir_path = os.path.abspath('')
    pythonpath = os.getenv('PYTHONPATH', '')
    pythonpath += dir_path
    os.environ['PYTHONPATH'] = pythonpath      

def generate_language_model():
    option = input("Would you like to save a step and generate the default language model now (y/n)? ")
    if option[0].lower() == 'y':
        os.system('pipenv run python language_models/gensim/generate_gensim_model.py')

def upgrades():
    os.system("pipenv run pip install --upgrade google-cloud-speech")        

def main(os_name):
    set_pythonpath()   
    setup_env()
    if os_name == "Windows":
        set_up_windows()
    elif os_name == "macOS" or os_name == "Darwin":
        set_up_mac() 
    elif os_name == "Linux" or os_name == 'Ubuntu':
        set_up_ubuntu()
    upgrades()    
    generate_language_model()

if __name__ == '__main__':
    sys_info = platform.uname()
    os_name = sys_info.system
    main(os_name)
    print(f"{60*'*'}\n*****    installation.py has completed execution    *****\n{60*'*'}") 

        