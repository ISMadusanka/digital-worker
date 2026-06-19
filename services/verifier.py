"""
Action Verification Service.

After each action (click, type, keypress), captures a fresh screenshot +
OCR pass and asks the LLM whether the action achieved its intended effect.
If not, it returns a suggested corrective action.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from langchain_openai import ChatOpenAI

from config import settings
from utils.logger import get_logger

log = get_logger(__name__)


VERIFICATION_PROMPT = """\
You are an action-verification assistant for a desktop automation system.

You are given:
1. The ACTION that was just performed (e.g., "Clicked button '4' at (191, 745)").
2. The UI STATE BEFORE the action.
3. The UI STATE AFTER the action.
4. The OVERALL GOAL the user is trying to achieve.

Your task is to determine whether the action achieved its intended effect by
comparing the before and after UI states.

Respond in EXACTLY this format (no extra text):

VERIFIED: true  OR  VERIFIED: false
EXPLANATION: <one-sentence explanation of what changed or didn't change>
CORRECTION: <if VERIFIED is false, describe what corrective action should be taken — e.g., "Click the CE button to clear, then click the correct button". If VERIFIED is true, write "none">
"""


@dataclass
class VerificationResult:
    """Result of verifying a single action."""

    verified: bool
    explanation: str
    suggested_correction: Optional[str] = None

    def __str__(self) -> str:
        status = "✅ VERIFIED" if self.verified else "❌ FAILED"
        msg = f"{status}: {self.explanation}"
        if not self.verified and self.suggested_correction:
            msg += f" | Suggested correction: {self.suggested_correction}"
        return msg


class ActionVerificationService:
    """Verifies whether an executed action achieved its intended effect."""

    def __init__(self) -> None:
        log.info("Initializing ActionVerificationService")
        self._llm = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=0,
            api_key=settings.OPENAI_API_KEY,
        )

    def verify(
        self,
        action_description: str,
        ui_state_before: str,
        ui_state_after: str,
        overall_goal: str,
    ) -> VerificationResult:
        """Compare before/after UI states and judge if the action was correct.

        Args:
            action_description: Human-readable description of the action taken.
            ui_state_before: Formatted UI elements string BEFORE the action.
            ui_state_after: Formatted UI elements string AFTER the action.
            overall_goal: The overarching goal the worker is trying to achieve.

        Returns:
            A ``VerificationResult`` with verified flag, explanation, and
            optional correction suggestion.
        """
        user_message = (
            f"OVERALL GOAL: {overall_goal}\n\n"
            f"ACTION PERFORMED: {action_description}\n\n"
            f"UI STATE BEFORE:\n{ui_state_before}\n\n"
            f"UI STATE AFTER:\n{ui_state_after}\n\n"
            f"Was this action correct? Respond in the required format."
        )

        log.info("Verifying action: %s", action_description)

        try:
            response = self._llm.invoke([
                ("system", VERIFICATION_PROMPT),
                ("user", user_message),
            ])
            return self._parse_response(response.content)
        except Exception as e:
            log.error("Verification LLM call failed: %s", e)
            # Fail-open: if verification itself errors, assume action was OK
            return VerificationResult(
                verified=True,
                explanation=f"Verification skipped due to error: {e}",
            )

    def _parse_response(self, text: str) -> VerificationResult:
        """Parse the structured LLM response into a VerificationResult."""
        lines = text.strip().splitlines()
        verified = True
        explanation = ""
        correction = None

        for line in lines:
            line_stripped = line.strip()
            upper = line_stripped.upper()

            if upper.startswith("VERIFIED:"):
                value = line_stripped.split(":", 1)[1].strip().lower()
                verified = value in ("true", "yes", "1")

            elif upper.startswith("EXPLANATION:"):
                explanation = line_stripped.split(":", 1)[1].strip()

            elif upper.startswith("CORRECTION:"):
                corr = line_stripped.split(":", 1)[1].strip()
                if corr.lower() not in ("none", "n/a", ""):
                    correction = corr

        log.info(
            "Verification result — verified=%s, explanation=%s",
            verified,
            explanation,
        )
        return VerificationResult(
            verified=verified,
            explanation=explanation,
            suggested_correction=correction,
        )
