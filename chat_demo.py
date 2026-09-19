"""Run python chat_demo.py, or python chat_demo.py --offline."""
import argparse
import os
import json

from dotenv import load_dotenv

from survey_intelligence.surveys import HOOS_JR
from survey_intelligence.extractor import keyword_extractor
from survey_intelligence.service import SurveyService


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    provider = "keyword" if args.offline else os.getenv("SURVEY_EXTRACTOR", "openai")
    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            parser.error("Set OPENAI_API_KEY in .env, or run with --offline.")
        from survey_intelligence.openai_extractor import OpenAIExtractor
        extractor = OpenAIExtractor()
    elif provider == "keyword":
        extractor = keyword_extractor
    else:
        parser.error("SURVEY_EXTRACTOR must be openai or keyword")
    service = SurveyService(HOOS_JR, extractor)
    turn = service.create_session()
    print(turn["prompt"])
    while turn["state"] not in {"complete", "escalated", "stopped"}:
        print(f"[{turn['answered_count']} of {turn['question_count']} answers confirmed]")
        try:
            transcript = input("> ")
        except (EOFError, KeyboardInterrupt):
            break
        turn = service.handle_turn(turn["session_id"], transcript)
        print(turn["prompt"])
    print(json.dumps(turn, indent=2))


if __name__ == "__main__":
    main()
