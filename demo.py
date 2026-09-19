from survey_intelligence import SurveyDefinition, SurveyEngine, SurveyQuestion


SURVEY = SurveyDefinition(
    id="knee-outcomes-demo",
    questions=(
        SurveyQuestion("stairs", "How much difficulty do you have going up or down stairs?", ("none", "mild", "moderate", "severe", "extreme")),
        SurveyQuestion("pain_walking", "How much pain do you experience while walking?", ("none", "mild", "moderate", "severe", "extreme")),
    ),
)


if __name__ == "__main__":
    engine = SurveyEngine(SURVEY)
    print("ASSISTANT:", engine.start())
    transcript = "Oh god, stairs are terrible. I have to pull myself up using the railing."
    print("PATIENT:", transcript)
    print("ASSISTANT:", engine.receive_transcript(transcript))
    print("PATIENT: Yeah")
    print("ASSISTANT:", engine.confirm("Yeah", "Yeah"))
    print("SNAPSHOT:", engine.snapshot())
