"""Official conference checklist templates used by the checklist endpoint."""

ARR_RESPONSIBLE_NLP_CHECKLIST = [
    {"id": "A1", "section": "A. For every submission", "text": "Did you describe the limitations of your work?"},
    {"id": "A2", "section": "A. For every submission", "text": "Did you discuss any potential risks of your work?"},
    {"id": "B1", "section": "B. Scientific artifacts", "text": "Did you cite the creators of artifacts you used?"},
    {"id": "B2", "section": "B. Scientific artifacts", "text": "Did you discuss the license or terms for use and / or distribution of any artifacts?"},
    {"id": "B3", "section": "B. Scientific artifacts", "text": "Did you discuss if your use of existing artifact(s) was consistent with their intended use, and for artifacts you create, do you specify intended use and whether that is compatible with the original access conditions?"},
    {"id": "B4", "section": "B. Scientific artifacts", "text": "Did you discuss the steps taken to check whether the data that was collected / used contains any information that names or uniquely identifies individual people or offensive content, and the steps taken to protect / anonymize it?"},
    {"id": "B5", "section": "B. Scientific artifacts", "text": "Did you provide documentation of the artifacts, e.g., coverage of domains, languages, linguistic phenomena, demographic groups represented, etc.?"},
    {"id": "B6", "section": "B. Scientific artifacts", "text": "Did you report relevant statistics like the number of examples, details of train / test / dev splits, etc. for the data that you used / created?"},
    {"id": "C1", "section": "C. Computational experiments", "text": "Did you report the number of parameters in the models used, the total computational budget (e.g., GPU hours), and computing infrastructure used?"},
    {"id": "C2", "section": "C. Computational experiments", "text": "Did you discuss the experimental setup, including hyperparameter search and best-found hyperparameter values?"},
    {"id": "C3", "section": "C. Computational experiments", "text": "Did you report descriptive statistics about your results (e.g., error bars around results, summary statistics from sets of experiments), and is it transparent whether you are reporting the max, mean, etc. or just a single run?"},
    {"id": "C4", "section": "C. Computational experiments", "text": "If you used existing packages (e.g., for preprocessing, normalization, or evaluation), did you report the implementation, model, and parameter settings used?"},
    {"id": "D1", "section": "D. Human annotators / participants", "text": "Did you report the full text of instructions given to participants, including e.g., screenshots, disclaimers of any risks to participants or annotators, etc.?"},
    {"id": "D2", "section": "D. Human annotators / participants", "text": "Did you report information about how you recruited and paid participants, and discuss if such payment is adequate given the participants' demographic?"},
    {"id": "D3", "section": "D. Human annotators / participants", "text": "Did you discuss whether and how consent was obtained from people whose data you're using/curating?"},
    {"id": "D4", "section": "D. Human annotators / participants", "text": "Was the data collection protocol approved (or determined exempt) by an ethics review board?"},
    {"id": "D5", "section": "D. Human annotators / participants", "text": "Did you report the basic demographic and geographic characteristics of the annotator population that is the source of the data?"},
    {"id": "E1", "section": "E. AI assistants", "text": "If you used any AI assistants, did you include information about your use?"},
]

NEURIPS_PAPER_CHECKLIST = [
    {"id": "1", "section": "Claims", "text": "Do the main claims made in the abstract and introduction accurately reflect the paper's contributions and scope?"},
    {"id": "2", "section": "Limitations", "text": "Did you discuss the limitations of your work?"},
    {"id": "3", "section": "Theory, Assumptions and Proofs", "text": "If you are including theoretical results, did you state the full set of assumptions of all theoretical results, and did you include complete proofs of all theoretical results?"},
    {"id": "4", "section": "Experimental Result Reproducibility", "text": "If the contribution is a dataset or model, what steps did you take to make your results reproducible or verifiable?"},
    {"id": "5", "section": "Open Access to Data and Code", "text": "If you ran experiments, did you include the code, data, and instructions needed to reproduce the main experimental results (either in the supplemental material or as a URL)?"},
    {"id": "6", "section": "Experimental Setting / Details", "text": "If you ran experiments, did you specify all the training details (e.g., data splits, hyperparameters, how they were chosen)?"},
    {"id": "7", "section": "Experiment Statistical Significance", "text": "Does the paper report error bars suitably and correctly defined or other appropriate information about the statistical significance of the experiments?"},
    {"id": "8", "section": "Experiments Compute Resource", "text": "For each experiment, does the paper provide sufficient information on the computer resources (type of compute workers, memory, time of execution) needed to reproduce the experiments?"},
    {"id": "9", "section": "Code Of Ethics", "text": "Have you read the NeurIPS Code of Ethics and ensured that your research conforms to it?"},
    {"id": "10", "section": "Broader Impacts", "text": "If appropriate for the scope and focus of your paper, did you discuss potential negative societal impacts of your work?"},
    {"id": "11", "section": "Safeguards", "text": "Do you have safeguards in place for responsible release of models with a high risk for misuse (e.g., pretrained language models)?"},
    {"id": "12", "section": "Licenses", "text": "If you are using existing assets (e.g., code, data, models), did you cite the creators and respect the license and terms of use?"},
    {"id": "13", "section": "Assets", "text": "If you are releasing new assets, did you document them and provide these details alongside the assets?"},
    {"id": "14", "section": "Crowdsourcing and Research with Human Subjects", "text": "If you used crowdsourcing or conducted research with human subjects, did you include the full text of instructions given to participants and screenshots, if applicable, as well as details about compensation (if any)?"},
    {"id": "15", "section": "IRB Approvals", "text": "Did you describe any potential participant risks and obtain Institutional Review Board (IRB) approvals (or an equivalent approval/review based on the requirements of your institution), if applicable?"},
    {"id": "16", "section": "Declaration of LLM usage", "text": "Does the paper describe the usage of LLMs if it is an important, original, or non-standard component of the core methods in this research?"},
]

CHECKLISTS = {
    "arr": {
        "name": "ARR Responsible NLP Research Checklist",
        "source": "https://aclrollingreview.org/responsibleNLPresearch/",
        "items": ARR_RESPONSIBLE_NLP_CHECKLIST,
    },
    "neurips": {
        "name": "NeurIPS Paper Checklist",
        "source": "https://neurips.cc/public/guides/PaperChecklist",
        "items": NEURIPS_PAPER_CHECKLIST,
    },
}
