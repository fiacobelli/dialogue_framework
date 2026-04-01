# Install Tutoring System

The Tutoring System has three modules, each in it's own folder: speech (a.k.a pauses_in_voice), nlu_helper and tutoring_system. This page has basic installation and/or execution instructions for each module. The following instructions use pip as a package manager and pipenv for creating a virtual environment. If you use a different package manager than pip or a different virtual environment than pipenv, refer to the READMEs for installation instructions. If you encounter any issues with installation or execution, consult the READMEs. 

First, clone the repository to your computer: [tutoring_system](https://github.com/fiacobelli/tutoring_system.wiki.git)

# Installations in the tutoring_system folder

*For Mac OS*, please first install `portaudio`. For this you need to install `homebrew`. Then, from the command line type `brew install portaudio --HEAD`

The recommended tool for installing the system is `pipenv`. With this tool, From your CLI, in the `tutoring_system` folder type:

    $pipenv install

Then you are done. Proceed to the *Installing NLTK and Spacy models* section. 

### Installation without pipenv.

If you want to change your system-wide settings, you can type this instead (not recommended):

    $pip install -r configuration/requirements.txt

If you want to install the system using `mamba` or `conda`, all the packages come from `conda-forge`.
To see all the packages required, open the file named `Pipenv` and look at the list of packages. Install them using `conda` or `mamba`.

## Installing NLTK and Spacy modules.

We need to install a couple of libraries for NLP. The first one is NLTK.
You will need to go into the python shell to download a few things from nltk. From your CLI, type:

`$pipenv run python`  to access the python shell. If you are not using pipenv, simply type `python`

Python will open a shell with `>>>` as the prompt. From there, type:
    >>> import nltk
    >>> nltk.download('stopwords')
    >>> nltk.download('punkt')
    >>> quit()  # to exit the python shell

Then, you need to install a spacy model. For this, run the following command on your terminal:

`$pipenv run python -m spacy download en_core_web_sm`   (any trouble running spacy, see [README](https://github.com/fiacobelli/tutoring_system/blob/main/speech/README.md))

For more information on installation: [tutoring_system README](https://github.com/fiacobelli/tutoring_system/blob/main/README.md).

For all subsequent commands, if the command says `python`, and you are using `pipenv`, please type `pipenv run` before the python command.
For example, `python myfile.py` becomes `pipenv run python myfile.py`.

# Generate a model

Remain in the main tutoring_system folder. 
To generate a language model, you must download a corpus from which to build the model. Download [all-senate-speeches.txt](https://www.dropbox.com/s/rbhpy3qtr5oudr2/all-senate-speeches.txt?dl=0) to the nlu_helper/resources folder.

Currently, the all-senate-speeches.txt file needs to be modified slightly. From the CLI, type:

    $python nlu_helper/corpus/bookend_file.py nlu_helper/corpus/all-senate-speeches.txt

Now you need to edit your PYTHONPATH:

     * if you are on a MAC OS: `$export PYTHONPATH=${PYTHONPATH}:.`

     * if you are on a Windows OS, running a normal shell (anaconda, cmd): `$set PYTHONPATH=%PYTHONPATH;.`

     * if you are on a Windows OS, running PowerShell: `$Env:PYTHONPATH += ";."`

You may ask model_generator.py for help in constructing a model:

    $ python nlu_helper/model_generator.py -h 

To generate a model to meet the specifications in tutoring_system/configuration/environment, you will need to run:

    $python nlu_helper/model_generator.py --action lsa -min_df 2 --score zeroone -svd_c 300 -truncate 300 -o all_senate

For more information about generating a model: [information on generating a language model/nlu_helper README](https://github.com/fiacobelli/tutoring_system/blob/main/nlu_helper/README.md).

### Final notes on installation

All the steps above are a one-time only steps, so don't worry if they take time.

For more information about the packages used here or for any other issues about installation, see the instructions in the README found in the speech folder [pauses_in_voice/speech installation](https://github.com/fiacobelli/tutoring_system/blob/main/speech/README.md).

# Run the Tutoring system:

In your CLI, run the command: 

    $python dialogue_application.py -f test.log 

Note: test.log is any arbitrary file where the user progress will be kept. User progress is saved when the dialogue ends, either by saying quit or because all content was covered.
Details are given on running dialogue_application.py towards the end of the original README: [how to run tutoring_system](https://github.com/fiacobelli/tutoring_system/blob/main/README.md).