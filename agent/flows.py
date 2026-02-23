"""Conversation flow state machine for Maya.

Tracks the current phase of a patient conversation and the data collected
so far.  The state machine is intentionally lightweight -- it does NOT
drive the LLM output directly, but rather provides structured metadata
that the pipeline can inspect for:

- Idle-timeout prompts ("Are you still there?")
- Post-call logging (which tools were used, duration, escalation flag)
- Analytics dashboards (state distribution, average turn count, etc.)

State transitions::

    GREETING -> INTENT_DETECTION
    INTENT_DETECTION -> BOOKING_COLLECT_INFO | FAQ_QUERY | ESCALATION | FAREWELL
    BOOKING_COLLECT_INFO -> BOOKING_CHECK_SLOTS
    BOOKING_CHECK_SLOTS -> BOOKING_CONFIRM
    BOOKING_CONFIRM -> FAREWELL
    FAQ_QUERY -> FAQ_ANSWER
    FAQ_ANSWER -> FAREWELL | INTENT_DETECTION  (follow-up question)
    ESCALATION -> FAREWELL
    FAREWELL -> IDLE
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from loguru import logger


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------


class ConversationState(enum.Enum):
    """Possible phases of a patient conversation with Maya."""

    GREETING = "greeting"
    INTENT_DETECTION = "intent_detection"
    BOOKING_COLLECT_INFO = "booking_collect_info"
    BOOKING_CHECK_SLOTS = "booking_check_slots"
    BOOKING_CONFIRM = "booking_confirm"
    FAQ_QUERY = "faq_query"
    FAQ_ANSWER = "faq_answer"
    ESCALATION = "escalation"
    FAREWELL = "farewell"
    IDLE = "idle"


# ---------------------------------------------------------------------------
# Valid transitions (source -> set of allowed targets)
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: dict[ConversationState, set[ConversationState]] = {
    ConversationState.GREETING: {
        ConversationState.INTENT_DETECTION,
    },
    ConversationState.INTENT_DETECTION: {
        ConversationState.BOOKING_COLLECT_INFO,
        ConversationState.FAQ_QUERY,
        ConversationState.ESCALATION,
        ConversationState.FAREWELL,
    },
    ConversationState.BOOKING_COLLECT_INFO: {
        ConversationState.BOOKING_CHECK_SLOTS,
        ConversationState.ESCALATION,
        ConversationState.FAREWELL,
    },
    ConversationState.BOOKING_CHECK_SLOTS: {
        ConversationState.BOOKING_CONFIRM,
        ConversationState.BOOKING_COLLECT_INFO,  # retry if no slots
        ConversationState.ESCALATION,
        ConversationState.FAREWELL,
    },
    ConversationState.BOOKING_CONFIRM: {
        ConversationState.FAREWELL,
        ConversationState.INTENT_DETECTION,  # "anything else?"
        ConversationState.ESCALATION,
    },
    ConversationState.FAQ_QUERY: {
        ConversationState.FAQ_ANSWER,
        ConversationState.ESCALATION,
    },
    ConversationState.FAQ_ANSWER: {
        ConversationState.FAREWELL,
        ConversationState.INTENT_DETECTION,  # follow-up question
        ConversationState.ESCALATION,
    },
    ConversationState.ESCALATION: {
        ConversationState.FAREWELL,
    },
    ConversationState.FAREWELL: {
        ConversationState.IDLE,
    },
    ConversationState.IDLE: set(),  # terminal
}


# ---------------------------------------------------------------------------
# Conversation context data class
# ---------------------------------------------------------------------------


@dataclass
class ConversationContext:
    """Tracks the current state and collected info during a conversation.

    Attributes:
        state: Current phase of the conversation.
        patient_name: Collected patient name (may be ``None`` until gathered).
        patient_phone: Collected patient phone number.
        doctor_name: Doctor the patient wants to see.
        visit_type: Type of visit (general/followup/specialist/urgent).
        preferred_date: Patient's preferred appointment date.
        slot_datetime: Confirmed slot datetime after availability check.
        tools_used: Ordered list of tool names invoked during this call.
        started_at: UTC timestamp when the conversation began.
        last_activity: UTC timestamp of the most recent user or agent turn.
        turn_count: Number of conversational turns (user + assistant).
        escalated: Whether this conversation was escalated to a human.
        transcript_lines: Accumulated transcript lines for call logging.
    """

    state: ConversationState = ConversationState.GREETING
    patient_name: str | None = None
    patient_phone: str | None = None
    doctor_name: str | None = None
    visit_type: str | None = None
    preferred_date: str | None = None
    slot_datetime: str | None = None
    tools_used: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    turn_count: int = 0
    escalated: bool = False
    transcript_lines: list[str] = field(default_factory=list)

    # -- State transitions --------------------------------------------------

    def transition(self, new_state: ConversationState) -> None:
        """Transition to a new conversation state.

        Logs the transition and validates it against the allowed transition
        map.  Invalid transitions are logged as warnings but still applied
        (the state machine is advisory, not blocking).

        Args:
            new_state: The target ``ConversationState``.
        """
        old_state = self.state
        allowed = _VALID_TRANSITIONS.get(old_state, set())

        if new_state not in allowed:
            logger.warning(
                "Unexpected state transition: {} -> {} (allowed: {})",
                old_state.value,
                new_state.value,
                [s.value for s in allowed],
            )
        else:
            logger.info(
                "State transition: {} -> {}",
                old_state.value,
                new_state.value,
            )

        self.state = new_state
        self.touch()

    # -- Tool usage tracking ------------------------------------------------

    def record_tool_use(self, tool_name: str) -> None:
        """Record that a tool was invoked during this conversation.

        Args:
            tool_name: The function name of the tool (e.g.
                ``"check_available_slots"``).
        """
        self.tools_used.append(tool_name)
        self.touch()
        logger.debug(
            "Tool recorded: {} (total tools used: {})",
            tool_name,
            len(self.tools_used),
        )

    # -- Activity / timeout tracking ----------------------------------------

    def touch(self) -> None:
        """Update the last-activity timestamp to the current UTC time."""
        self.last_activity = datetime.now(timezone.utc)

    def increment_turn(self) -> None:
        """Increment the turn counter and update activity timestamp."""
        self.turn_count += 1
        self.touch()
        logger.debug("Turn count incremented to {}", self.turn_count)

    def is_timed_out(self, timeout_seconds: int = 10) -> bool:
        """Check if the conversation has been idle for too long.

        Args:
            timeout_seconds: Maximum allowed idle time in seconds.  The
                default (10 s) matches the CLAUDE.md spec for prompting
                "Are you still there?"

        Returns:
            ``True`` if the elapsed time since the last activity exceeds
            *timeout_seconds*.
        """
        elapsed = (datetime.now(timezone.utc) - self.last_activity).total_seconds()
        timed_out = elapsed >= timeout_seconds
        if timed_out:
            logger.info(
                "Conversation timed out | idle={:.1f}s threshold={}s",
                elapsed,
                timeout_seconds,
            )
        return timed_out

    def duration_seconds(self) -> int:
        """Calculate the total conversation duration in whole seconds.

        Returns:
            Elapsed seconds from ``started_at`` to now (or to
            ``last_activity`` if the conversation is in IDLE state).
        """
        end = (
            self.last_activity
            if self.state == ConversationState.IDLE
            else datetime.now(timezone.utc)
        )
        return int((end - self.started_at).total_seconds())

    # -- Transcript management ----------------------------------------------

    def add_transcript_line(self, role: str, text: str) -> None:
        """Append a line to the running transcript.

        Args:
            role: Speaker identifier (``"user"`` or ``"maya"``).
            text: The spoken text.
        """
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        line = f"[{timestamp}] {role.upper()}: {text}"
        self.transcript_lines.append(line)
        logger.debug("Transcript +1 line | role={} len={}", role, len(text))

    def get_transcript(self) -> str:
        """Return the full transcript as a single newline-separated string.

        Returns:
            Complete conversation transcript.
        """
        return "\n".join(self.transcript_lines)

    # -- Data collection helpers --------------------------------------------

    def set_patient_info(
        self,
        *,
        name: str | None = None,
        phone: str | None = None,
    ) -> None:
        """Update patient identification fields.

        Only non-``None`` values are applied.

        Args:
            name: Patient's full name.
            phone: Patient's phone number.
        """
        if name is not None:
            self.patient_name = name
            logger.debug("Patient name set: {}", name)
        if phone is not None:
            self.patient_phone = phone
            logger.debug("Patient phone set: {}", phone)
        self.touch()

    def set_booking_info(
        self,
        *,
        doctor_name: str | None = None,
        visit_type: str | None = None,
        preferred_date: str | None = None,
        slot_datetime: str | None = None,
    ) -> None:
        """Update appointment booking fields.

        Only non-``None`` values are applied.

        Args:
            doctor_name: Requested doctor's name.
            visit_type: Visit type string.
            preferred_date: Preferred date in ISO format.
            slot_datetime: Confirmed slot datetime in ISO format.
        """
        if doctor_name is not None:
            self.doctor_name = doctor_name
        if visit_type is not None:
            self.visit_type = visit_type
        if preferred_date is not None:
            self.preferred_date = preferred_date
        if slot_datetime is not None:
            self.slot_datetime = slot_datetime
        self.touch()
        logger.debug(
            "Booking info updated | doctor={} type={} date={} slot={}",
            self.doctor_name,
            self.visit_type,
            self.preferred_date,
            self.slot_datetime,
        )

    def mark_escalated(self) -> None:
        """Flag this conversation as having been escalated to a human."""
        self.escalated = True
        self.transition(ConversationState.ESCALATION)
        logger.warning("Conversation marked as ESCALATED")

    # -- Export for call logging ---------------------------------------------

    def to_call_log(self) -> dict[str, Any]:
        """Convert the conversation context to a dict for saving as a CallLog.

        The returned dict matches the ``CallLogCreate`` Pydantic schema
        expected by ``POST /api/calls/``.

        Returns:
            Dict with keys: ``patient_phone``, ``duration_seconds``,
            ``transcript``, ``tools_used``, ``escalated``.
        """
        duration = self.duration_seconds()
        transcript = self.get_transcript()

        call_data: dict[str, Any] = {
            "patient_phone": self.patient_phone or "unknown",
            "duration_seconds": duration,
            "transcript": transcript if transcript else "(no transcript)",
            "tools_used": list(set(self.tools_used)),  # deduplicate
            "escalated": self.escalated,
        }

        logger.info(
            "Exporting call log | phone={} duration={}s turns={} "
            "tools={} escalated={}",
            call_data["patient_phone"],
            duration,
            self.turn_count,
            call_data["tools_used"],
            self.escalated,
        )

        return call_data

    # -- Repr ---------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<ConversationContext state={self.state.value} "
            f"turns={self.turn_count} "
            f"patient={self.patient_name!r} "
            f"doctor={self.doctor_name!r} "
            f"escalated={self.escalated}>"
        )
