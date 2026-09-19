"""HOOS, JR. transcribed from the supplied image; section stems folded into prompts."""
from .models import SurveyDefinition, SurveyQuestion

OPTIONS = ("none", "mild", "moderate", "severe", "extreme")

HOOS_JR = SurveyDefinition(
    id="hoos-jr",
    title="HOOS, JR. HIP SURVEY",
    instructions=(
        "This survey asks for your view about your hip. This information will help "
        "us keep track of how you feel about your hip and how well you are able to "
        "do your usual activities. Answer every question with only one answer for "
        "each question. If you are unsure about how to answer a question, please "
        "give the best answer you can. Think about the last week. "
        "Your choices are None, Mild, Moderate, Severe, or Extreme. "
        "I will confirm each answer with you. You can say stop to end the survey."
    ),
    questions=(
        SurveyQuestion("pain_stairs", "What amount of hip pain have you experienced in the last week when going up or down stairs?", OPTIONS),
        SurveyQuestion("pain_uneven_surface", "What amount of hip pain have you experienced in the last week when walking on an uneven surface?", OPTIONS),
        SurveyQuestion("function_rising", "What degree of difficulty have you experienced in the last week due to your hip when rising from sitting?", OPTIONS),
        SurveyQuestion("function_bending", "What degree of difficulty have you experienced in the last week due to your hip when bending to the floor to pick up an object?", OPTIONS),
        SurveyQuestion("function_bed", "What degree of difficulty have you experienced in the last week due to your hip when lying in bed (turning over, maintaining hip position)?", OPTIONS),
        SurveyQuestion("function_sitting", "What degree of difficulty have you experienced in the last week due to your hip when sitting?", OPTIONS),
    ),
)
