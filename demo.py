from survey_intelligence import SurveyEngine
from survey_intelligence.surveys import HOOS_JR


SURVEY = HOOS_JR


if __name__ == "__main__":
    engine = SurveyEngine(SURVEY)
    print("ASSISTANT:", engine.start())
    for answer in ("mild", "moderate", "severe", "mild", "none", "moderate"):
        print("PATIENT:", answer)
        print("ASSISTANT:", engine.handle_turn(answer))
        print("PATIENT: Yes")
        print("ASSISTANT:", engine.handle_turn("Yes"))
    print("SNAPSHOT:", engine.snapshot())
