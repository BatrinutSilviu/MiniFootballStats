"""
Optional: asks Claude to turn the computed stats and rule-based insights into
a plain-language coaching report. Only enabled when an Anthropic API key is
configured — everything else in the app runs locally and free.
"""
from pydantic import BaseModel

from app.config import ANTHROPIC_API_KEY, COACH_MODEL

SYSTEM_PROMPT = """You are an experienced amateur mini-football (5-a-side / futsal-style) coach.
You receive statistics automatically extracted from a video of one match by computer vision,
plus rule-based observations computed from them. Write feedback the players can act on at their
next training session.

The numbers are estimates: ball detection, team assignment and event detection are imperfect,
and with a moving camera players are only measured while in view. Respect each observation's
confidence level and the data-quality notes; never present low-confidence findings as facts,
and do not invent events or numbers that are not in the data. Teams are called "Team A" and
"Team B" (with their detected jersey colors). Use simple language, no analytics jargon."""


class Point(BaseModel):
    title: str
    explanation: str


class Lesson(BaseModel):
    title: str
    explanation: str
    drill: str


class TeamFeedback(BaseModel):
    team: str  # "team_a" or "team_b"
    headline: str
    strengths: list[Point]
    lessons: list[Lesson]


class CoachReport(BaseModel):
    summary: str
    teams: list[TeamFeedback]
    caveats: list[str]


def coach_available() -> bool:
    if not ANTHROPIC_API_KEY:
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _compact_results(results: dict) -> dict:
    """Drop bulky per-frame data the model doesn't need."""
    keep = ("pitch", "duration_s", "team_colors", "teams", "quality", "insights")
    out = {k: results[k] for k in keep if k in results}
    out["players"] = [
        {k: v for k, v in p.items() if k != "heatmap"} for p in results.get("players", [])
    ]
    out["key_events"] = [e for e in results.get("events", []) if e["type"] in ("shot", "keeper_handling")]
    return out


def generate_coach_report(results: dict) -> dict:
    import json

    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.beta.messages.parse(
        model=COACH_MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[
            {
                "role": "user",
                "content": "Match data:\n\n"
                + json.dumps(_compact_results(results), indent=1)
                + "\n\nWrite the coaching report for both teams: 2-4 strengths and 2-4 lessons each, every lesson with one concrete drill.",
            }
        ],
        output_format=CoachReport,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise RuntimeError(f"Claude did not return a report (stop reason: {response.stop_reason})")
    return {"model": response.model, **response.parsed_output.model_dump()}
