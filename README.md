# Dialogue Framework

A modular dialogue system framework implementing the Traum & Larsson information-state architecture. Supports multiple applications through swappable components.

---

## Kidney Transplant Microsite Builder (Web App)

A voice-enabled web application that interviews kidney transplant patients and generates personalized donor appeal microsites.

### Features
- Conversational interview with animated avatar (SitePal)
- Voice input/output with speech recognition
- Photo upload via QR code (mobile-friendly)
- LLM-powered microsite generation
- Multi-language support (English, Spanish, Arabic)

### Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   python -m spacy download en_core_web_sm
   ```

2. **Configure environment:**
   Create a `.env` file with:
   ```
   LLM_PROVIDER=azure_openai
   LLM_MODEL=gpt-6-astra
   AZURE_OPENAI_BASE_URL=https://luc-research-ai-resource.services.ai.azure.com/openai/v1/
   AZURE_OPENAI_API_KEY=your_azure_openai_key
   GROQ_API_KEY=your_groq_key_for_whisper
   FLASK_SECRET_KEY=your_secret_key
   ```

3. **Run the web app:**
   ```bash
   export PYTHONPATH=.
   python -m web.app
   ```

   Open http://localhost:5000 in your browser.

### Project Structure

```
web/                  # Flask application
├── app.py            # Entry point and routes
├── routes_api.py     # API endpoints
├── routes_photos.py  # Photo upload handling
├── session.py        # Session management
├── microsite.py      # Microsite generation
├── goal_interview.py # Interview goal logic
└── llm_provider.py   # LLM provider integration

templates/            # HTML templates
static/               # CSS, JS, images
prompts/              # System prompts
domains/              # Knowledge base JSON
```

---

# CLI Tutoring System (Original)

This project engages users by voice in a question and answer dialogue. Sessions begin with custom messages from the Tutoring System, then moves on to ask questions related to breast cancer and breast cancer survivorship. After asking a question, the system waits for a response from the user, and the system can be configured to utilize a sentence detection algorithm which enables the user to pause while speaking. Answers are evaluated for completeness, and the system's behavior to incomplete answers can be configured.

---

## The system is configured through a .env file. In the .env file are:

### Names

1) the names of modules to be used as a string, without the .py extension.
2) name of speech service file (CLOUDSPEECH)
3) name of language model used for scoring the similarity of sentence pairs (SIMILARITY_MODEL)
4) name of training file that contains custom messages and learning units (TRAINING_FILE)
5) name of training log that stores runtime logging data (TUTORING_LOG)

#### Example
Save these in a file called `.env` Yes. just like that. For an up to date example, look into the `configuration/environment.py`
```
#language models
SIMILARITY_MODEL= "lsi_model_wiki_cancer_54037x300"
SIMILARITY_MODULE = "similarity"
#speech service
CLOUDSPEECH = "speech/cloudspeech.json"
#content
TRAINING_FILE = "domains/mohamed_video1.json"
#modules
SPEECH_INTERFACE = 'speech_system'
DIALOGUE_MANAGER = 'dialogue_manager'
INFORMATION_STATE='information_state'
GOAL_MANAGER='goal_manager'
RULES_MANAGER='rules'
NLU='nlu'
NLG='nlg'
#logs
TUTORING_LOG='tutoring.log'
#thresholds
##### goal
NUM_ATTEMPTS_THRESHOLD='2'
SIMILARITY_THRESHOLD='0.80'
#flags
BYPASS_SENTENCE_COMPLETION = 'False'
# policies
##### goal
ACTION_FOR_INCOMPLETE_ANSWERS = 'table'
```

### Thresholds, Flags, Policies

Additional behavior of the system can be configured through these

For example, if the `action_for_incomplete_answers` is `table` and the `num_attempts_threshold` is `2`,

the system will allow two attempts at a question, then move onto the next question. 

---

### Prerequisites

* [Python](https://www.python.org/downloads/)
* [Git](https://git-scm.com/downloads)
* An IDE (eg: [VS code](https://code.visualstudio.com/))
* [Pipenv](https://pipenv.pypa.io/en/latest/installation.html)

---

### Getting started

* Clone the repository in a designated directory
``$ git clone https://github.com/fiacobelli/tutoring_system.git``
* Move to the repository
`$ cd tutoring_system`

---

## System Installation

### Automatic Installation

An installation script has been provided to:

1) set up virtual environment with Pipenv   ([Information on Pipenv by its Creator](https://pipenv.kennethreitz.org/en/latest/))
2) install all necessary packages from requirements.txt
3) download any modules or files used by system
4) create the .env file for configuration-environment
5) set PYTHONPATH, so python knows where to look for modules
6) offer to generate the default language model, and thereby skip generating the language model separately

#### To run the installation script

from the tutoring_system folder, in the command line interface, type:

`$ python installation.py`

when the installation script has finished running, the following message will appear:

`************************************************************`

`*****    installation.py has completed execution    *****`

`************************************************************`

---

### Manual Installation

If one prefers to install the system on their own, or if the automatic installation script is unable to perform one of the above tasks:

1) Install Pipenv. This may be as simple as:

`$ pip install pipenv`

Or you may refer to the installation documentation:
[Pip Install info for Pipenv](https://pypi.org/project/pipenv/)

Additionally, [Information on Pipenv by its Creator](https://pipenv.kennethreitz.org/en/latest/)

2) The majority of packages can be installed with:

`$pipenv run pip install -r requirements.txt`  ([[requirements.txt]](requirements.txt))

`$pipenv run pip install pyaudio`

To find out what packages have been installed in your Pipenv, you can run `pipenv run pip freeze` or `pipenv run pip list`

If you are NOT on a Windows Operating System, portaudio will also need to be installed

#### For macOS:

 `$brew install portaudio --HEAD` should do the trick.

If this does not work, you may need to update your xcode-cli tools. The messages from `brew` will tell
you how to do this.

#### For Linux/Ubuntu:

`$sudo apt-get install libasound-dev`

`$sudo apt-get install portaudio19-dev`

`$sudo apt-get install portaudio2`

`$sudo apt-get install portaudioccp0`

`$sudo apt-get install espeak`

3) Download any modules or files used by system:

 `$pipenv run python -m spacy download en_core_web_sm`

   It may be necessary to upgrade cloud-speech:

`$pipenv run pip install --upgrade google-cloud-speech`


4) Create the .env file for configuration-environment:

In the main tutoring_system folder, create an empty file called `.env`

From the tutoring_sytem/configuration folder, copy the contents of `environment.py`

Paste the copied contents in the empty `.env` file

5) Set the PYTHONPATH variable, so python knows where to look for modules:

#### For Windows, running a normal shell (anaconda, cmd):

`$set PYTHONPATH=%PYTHONPATH;.`

#### For Windows, running on Powershell:

`$Env:PYTHONPATH += “;.”`

#### For macOS, Linux or Ubuntu:

`$export PYTHONPATH=${PYTHONPATH}:.`

6) To generate the default language model:

`$pipenv run python language_models/gensim/generate_gensim_model.py`

If anyone would like to additionally create a custom model, using the `all-senate-speeches` corpus, [follow these instructions](language_models\custom\README.md) 

---



## Running the Tutoring system

In the CLI, run the command:

`$pipenv run python dialogue_application.py -f test.log`

NOTE: `test.log` is any arbitrary file where the user progress will be kept. User progress is saved when the dialogue ends, either by saying `quit` or because all content was covered.

---

## Creating content for tutoring.

Content can be created, configured and downloaded from this [Configuration Tool for Content Creators](https://github.com/fiacobelli/ConfigTool)

The content to be tutored resides in a JSON file formated like this: First, a set of general purpose messages, and then the content divided in units, topics and paragraphs. Paragraphs may have several questions and keywords associated with them like so:

`
{
		 "unit_id": 2,
		 "name": "Surgery",
		 "topics": [
			 {
				 "topic_id": 1,
				 "header": "Mastectomy and Lumpectomy",
				 "contents": [
					 {
						 "paragraph_id": 1,
						 "text": "cancer 1",
						 "text_alt": [],
						 "question": "Can you tell me about surgical treatments for breast cancer?",
						 "alt_question": ["What can you tell me about surgery for breast cancer?",""],
						 "keywords": ["",""]
					 },
					 {
						 "paragraph_id": 2,
						 "text": "cancer 2",
						 "text_alt": [],
						 "question": "",
						 "alt_question": ["",""],
						 "keywords": ["",""]
					 },
					 {
						 "paragraph_id": 3,
						 "text": "cancer 3",
						 "text_alt": [],
						 "question": "",
						 "alt_question": ["",""],
						 "keywords": ["",""]
					 },
					 {
						 "paragraph_id": 4,
						 "text": "cancer 4",
						 "text_alt": [],
						 "question": "",
						 "alt_question": ["",""],
						 "keywords": ["",""]
					 },
					 {
						 "paragraph_id": 5,
						 "text": "cancer 5",
						 "text_alt": [],
						 "question": "",
						 "alt_question": ["",""],
						 "keywords": ["",""]
					 }
				 ]
			 }
		 ]
	 }
     `
