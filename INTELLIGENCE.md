# Survey intelligence skeleton

This is the first vertical slice: patient transcript -> constrained extraction -> patient confirmation -> saved response.

Guarantees:

- The survey definition owns exact question order and allowed values.
- The extractor only proposes a value for the current question.
- Nothing is saved until the patient confirms.
- Raw transcript/evidence is retained beside the structured response.
- Safety phrases stop the survey and create a clinician-review flag.
- The intelligence layer never diagnoses, recommends treatment, or selects the next question.

Run `python demo.py` and `python -m pytest`.

Replace `keyword_extractor` with the voice provider's structured LLM adapter, but keep its contract narrow: return one allowed option, a confidence score, and the evidence from the patient's words. The engine remains the source of truth for progression and persistence.
