"""Deterministic offline provider for tests and key-less demos.

Produces module-shaped output so the full product can be demoed without spend.
"""

from __future__ import annotations

import re

from app.llm.base import LLMRequest, LLMResponse


def _input(req: LLMRequest) -> str:
    m = re.search(r"<user_input>\n?(.*?)\n?</user_input>", req.user, re.S)
    return (m.group(1) if m else req.user).strip()


def _first_words(text: str, n: int = 12) -> str:
    words = text.split()
    return " ".join(words[:n]) + ("…" if len(words) > n else "")


def _sql_for(question: str) -> str:
    q = question.lower()
    if "ticket" in q:
        return (
            "SELECT category, COUNT(*) AS tickets, ROUND(AVG(csat), 2) AS avg_csat\n"
            "FROM tickets\nGROUP BY category\nORDER BY tickets DESC\nLIMIT 20;"
        )
    if "plan" in q or "revenue" in q or "mrr" in q:
        return (
            "SELECT p.name AS plan, COUNT(*) AS active_subs,\n"
            "       ROUND(SUM(p.monthly_price), 2) AS mrr_usd\n"
            "FROM subscriptions s JOIN plans p ON p.id = s.plan_id\n"
            "WHERE s.status = 'active'\nGROUP BY p.name\nORDER BY mrr_usd DESC\nLIMIT 20;"
        )
    if "device" in q or "phone" in q:
        return (
            "SELECT make, COUNT(*) AS devices\nFROM devices\n"
            "GROUP BY make\nORDER BY devices DESC\nLIMIT 20;"
        )
    if "state" in q:
        return (
            "SELECT state, COUNT(*) AS customers\nFROM customers\n"
            "GROUP BY state\nORDER BY customers DESC\nLIMIT 20;"
        )
    return (
        "SELECT segment, COUNT(*) AS customers\nFROM customers\n"
        "GROUP BY segment\nORDER BY customers DESC\nLIMIT 20;"
    )


def _respond(module_id: str, text: str) -> str:
    gist = _first_words(text)
    if module_id == "career_coach":
        return (
            "### Match summary\n**Estimated match: 78%** (demo mode)\n\n"
            "### Strengths\n- Leadership scope and delivery track record align with the role\n"
            "- Platform modernization experience maps to the technical mandate\n\n"
            "### Gaps to address\n- Quantify business impact (revenue, cost, time) in the top 3 bullets\n"
            "- Mirror 3–4 keywords from the job description verbatim\n\n"
            "### Rewritten bullet (STAR)\n- Led a cross-functional team to modernize the data "
            "platform, cutting pipeline cost by X% and time-to-insight by Y%.\n\n"
            f"_Based on: “{gist}”_"
        )
    if module_id == "research_summarizer":
        return (
            "### Executive summary\nThe material argues for a focused, measurable approach; "
            "the main decision is scope and sequencing.\n\n"
            "### Key points\n1. Core claim restated plainly\n2. Supporting evidence\n"
            "3. Risks or counter-arguments\n4. Cost or effort implications\n5. Recommended next step\n\n"
            f"_Source excerpt: “{gist}”_"
        )
    if module_id == "sql_assistant":
        return (
            f"```sql\n{_sql_for(text)}\n```\n\n"
            "**What this does:** aggregates the sample telecom data to answer your question, "
            "sorted by the largest groups first."
        )
    if module_id == "status_report":
        return (
            "**Overall status: 🟢 Green**\n\n### Wins\n- Key milestone delivered on schedule\n\n"
            "### Risks\n- Dependency on partner team for integration testing\n\n"
            "### Asks\n- Decision on scope for next sprint by Friday\n\n"
            "### Next week\n- Complete integration tests; begin UAT\n\n"
            f"_From notes: “{gist}”_"
        )
    if module_id == "requirements_analyst":
        return (
            "### User stories\n| ID | Story | Priority |\n|---|---|---|\n"
            "| US-1 | As a user, I want the core capability so that I reach my goal faster | Must |\n"
            "| US-2 | As an admin, I want to monitor usage so that I control cost | Should |\n\n"
            "### Acceptance criteria (Gherkin)\n```gherkin\nScenario: Successful path\n"
            "  Given an approved user\n  When they complete the action\n"
            "  Then the result is saved and confirmed\n```\n\n"
            "### Approach\n1. Clarify success metric\n2. Thin vertical slice\n3. Test with 5 users\n\n"
            "### Open questions\n- Who is the decision owner?\n- What is the target date?\n\n"
            f"_Raw ask: “{gist}”_"
        )
    return f"Demo response for: {gist}"


class FakeProvider:
    name = "fake"

    def complete(self, req: LLMRequest, api_key: str) -> LLMResponse:
        text = _respond(req.module_id, _input(req))
        tokens_in = max(1, (len(req.system) + len(req.user)) // 4)
        tokens_out = max(1, len(text) // 4)
        return LLMResponse(text, tokens_in, tokens_out, req.model or "fake-demo")
