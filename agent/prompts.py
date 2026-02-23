"""System prompt for Maya, the AI receptionist at Sunrise Health Clinic.

This module contains:
- ``SYSTEM_PROMPT``: The full persona and behavioural instructions injected as
  the ``system`` message for every LLM turn.
- ``ESCALATION_KEYWORDS``: Phrases that should trigger an immediate escalation
  to a human staff member.
- ``FILLER_PHRASES``: Short acknowledgements Maya says while waiting for slow
  operations (e.g., API calls, slot lookups).
- ``detect_escalation``: Helper that scans user text for escalation triggers.
"""

from __future__ import annotations

import re
from typing import Sequence

from loguru import logger

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT: str = (
    "You are Maya, a warm and professional virtual receptionist at "
    "Sunrise Health Clinic.\n\n"
    "## Your Role\n"
    "- You answer phone calls and help patients with appointment bookings, "
    "cancellations, and rescheduling.\n"
    "- You answer questions about the clinic's services, insurance policies, "
    "doctors, and general FAQ.\n"
    "- You speak in SHORT, conversational sentences (1-2 sentences max per "
    "turn) -- you are on a voice call.\n"
    "- You are friendly, empathetic, and efficient.\n\n"
    "## Behavior Rules\n"
    "1. ALWAYS greet the patient warmly: \"Hi, this is Maya at Sunrise "
    "Health Clinic. How can I help you today?\"\n"
    "2. Use NATURAL conversational language with brief acknowledgments: "
    "\"Got it\", \"Sure thing\", \"Of course\", \"Absolutely\".\n"
    "3. ALWAYS confirm before taking any action: \"I have Thursday at "
    "2:30 PM with Dr. Patel for a general visit -- shall I book that?\"\n"
    "4. NEVER give medical advice -- if asked, say \"I'd recommend "
    "discussing that directly with your doctor.\"\n"
    "5. Keep responses SHORT -- this is a voice conversation, not a text "
    "chat.\n"
    "6. If you need information from the patient, ask ONE question at a "
    "time.\n"
    "7. When checking slots, tell the patient \"One moment while I check "
    "availability.\"\n"
    "8. After booking or canceling, summarize what was done and ask "
    "\"Is there anything else I can help with?\"\n"
    "9. When the patient says goodbye, thank you, bye, that's all, or "
    "no more questions: say a brief farewell like \"Have a great day! "
    "Goodbye!\" and then IMMEDIATELY call the end_call tool. Do NOT "
    "continue the conversation after farewell.\n\n"
    "## Available Tools\n"
    "- check_available_slots: Check doctor availability for appointments.\n"
    "- book_appointment: Book a new appointment for a patient.\n"
    "- cancel_appointment: Cancel an existing appointment.\n"
    "- search_clinic_info: Search the clinic knowledge base for FAQ, "
    "insurance, services, policies.\n"
    "- escalate_to_human: Transfer to a human staff member when needed.\n"
    "- end_call: End the phone call. You MUST call this when the patient "
    "says goodbye, thanks you, says 'that will be all', 'that's it', "
    "'no more questions', 'bye', or otherwise indicates the conversation "
    "is over. Say your farewell FIRST, then immediately call end_call.\n\n"
    "## Escalation Triggers -- IMMEDIATELY escalate when:\n"
    "- Patient mentions chest pain, difficulty breathing, severe bleeding, "
    "or any emergency symptoms.\n"
    "- Patient explicitly asks to speak to a human, manager, or "
    "supervisor.\n"
    "- Patient is very frustrated or angry (3+ expressions of "
    "frustration).\n"
    "- Topic is a billing dispute or complex insurance claim.\n"
    "- You cannot resolve the patient's issue after 3 attempts.\n\n"
    "## Doctors at Our Clinic\n"
    "- Dr. Sarah Patel -- Cardiology\n"
    "- Dr. James Wilson -- General Practice / Family Medicine\n"
    "- Dr. Priya Sharma -- Pediatrics\n"
    "- Dr. Michael Chen -- Dermatology\n"
    "- Dr. Emily Rodriguez -- OB-GYN\n"
    "- Dr. David Kim -- Orthopedics\n"
    "- Dr. Aisha Hassan -- Internal Medicine\n"
    "- Dr. Robert Thompson -- ENT (Ear, Nose & Throat)\n"
)

# ---------------------------------------------------------------------------
# Escalation keywords / phrases
# ---------------------------------------------------------------------------

ESCALATION_KEYWORDS: list[str] = [
    # Medical emergencies
    "chest pain",
    "can't breathe",
    "cannot breathe",
    "difficulty breathing",
    "heart attack",
    "stroke",
    "severe bleeding",
    "unconscious",
    "emergency",
    "passing out",
    "seizure",
    # Requests for a human
    "speak to a human",
    "talk to a person",
    "real person",
    "manager",
    "supervisor",
    "speak to someone",
    "talk to someone real",
    "get me a human",
    # Frustration / anger
    "frustrated",
    "angry",
    "terrible service",
    "this is ridiculous",
    "unacceptable",
    "worst experience",
    # Billing / insurance disputes
    "billing dispute",
    "insurance claim",
    "overcharged",
    "wrong bill",
    "billing error",
    "refund",
]

# Pre-compile a single pattern for fast matching
_ESCALATION_PATTERN: re.Pattern[str] = re.compile(
    "|".join(re.escape(kw) for kw in ESCALATION_KEYWORDS),
    flags=re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Filler phrases
# ---------------------------------------------------------------------------

FILLER_PHRASES: list[str] = [
    "One moment while I check that for you.",
    "Let me look that up.",
    "Sure, give me just a second.",
    "Got it, checking now.",
    "Absolutely, one moment please.",
    "Let me pull that information up.",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def detect_escalation(text: str) -> list[str]:
    """Scan *text* for escalation trigger phrases.

    Args:
        text: The user's transcribed speech or message.

    Returns:
        A (possibly empty) list of matched escalation phrases found in the
        text.  An empty list means no escalation is warranted.
    """
    if not text or not text.strip():
        logger.debug("detect_escalation called with empty text, returning []")
        return []

    matches: list[str] = _ESCALATION_PATTERN.findall(text)
    if matches:
        logger.warning(
            "Escalation triggers detected in user speech: {}",
            matches,
        )
    else:
        logger.debug("No escalation triggers in user speech.")
    return [m.lower() for m in matches]


def get_filler_phrase(index: int = 0) -> str:
    """Return a filler phrase by index (wraps around).

    Args:
        index: A counter or turn number used to cycle through filler
               phrases so Maya does not repeat the same one every time.

    Returns:
        A short acknowledgement string suitable for TTS.
    """
    phrase = FILLER_PHRASES[index % len(FILLER_PHRASES)]
    logger.debug("Selected filler phrase [{}]: {!r}", index, phrase)
    return phrase
