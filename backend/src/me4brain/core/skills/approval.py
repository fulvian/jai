"""Skill Approval Manager - HITL approval flow per skill cristallizzate.

Gestisce l'approvazione umana delle skill prima di salvarle su disco.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid

import structlog

from me4brain.core.skills.types import Skill

logger = structlog.get_logger(__name__)


class ApprovalStatus(Enum):
    """Status di approvazione skill."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class PendingSkill:
    """Skill in attesa di approvazione."""

    id: str
    skill: Skill
    risk_level: str  # SAFE, NOTIFY, CONFIRM
    tool_chain: list[str]
    created_at: datetime
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewed_at: Optional[datetime] = None
    reviewer_note: Optional[str] = None
    expires_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Converte a dict per API response."""
        return {
            "id": self.id,
            "name": self.skill.name,
            "description": self.skill.description,
            "risk_level": self.risk_level,
            "tool_chain": self.tool_chain,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }


class SkillApprovalManager:
    """Gestisce la coda di approvazione per skill cristallizzate.

    Implementa HITL flow:
    1. Skill CONFIRM-level va in coda pending
    2. API endpoint permette visualizzazione/approvazione
    3. Skill approvate vengono salvate su disco

    Skill SAFE/NOTIFY bypassano la coda.
    """

    def __init__(self, auto_approve_safe: bool = True):
        """Inizializza manager.

        Args:
            auto_approve_safe: Se True, skill SAFE vengono auto-approvate
        """
        self._pending: dict[str, PendingSkill] = {}
        self._approved: dict[str, PendingSkill] = {}
        self._rejected: dict[str, PendingSkill] = {}
        self._auto_approve_safe = auto_approve_safe

        # Callbacks
        self._on_approved: Optional[callable] = None
        self._on_rejected: Optional[callable] = None

    def set_callbacks(
        self,
        on_approved: Optional[callable] = None,
        on_rejected: Optional[callable] = None,
    ) -> None:
        """Imposta callback per eventi approvazione."""
        self._on_approved = on_approved
        self._on_rejected = on_rejected

    async def submit_for_approval(
        self,
        skill: Skill,
        risk_level: str,
        tool_chain: list[str],
    ) -> PendingSkill:
        """Sottomette skill per approvazione.

        Args:
            skill: Skill cristallizzata
            risk_level: SAFE, NOTIFY, CONFIRM
            tool_chain: Lista tool usati

        Returns:
            PendingSkill con stato appropriato
        """
        pending_id = str(uuid.uuid4())[:8]

        pending = PendingSkill(
            id=pending_id,
            skill=skill,
            risk_level=risk_level,
            tool_chain=tool_chain,
            created_at=datetime.now(),
        )

        # Auto-approve SAFE skills
        if risk_level == "SAFE" and self._auto_approve_safe:
            pending.status = ApprovalStatus.APPROVED
            pending.reviewed_at = datetime.now()
            pending.reviewer_note = "Auto-approved (SAFE level)"
            self._approved[pending_id] = pending

            logger.info(
                "skill_auto_approved",
                skill_name=skill.name,
                risk_level=risk_level,
            )

            if self._on_approved:
                await self._on_approved(pending)

            return pending

        # CONFIRM skills go to pending queue
        self._pending[pending_id] = pending

        logger.info(
            "skill_pending_approval",
            skill_id=pending_id,
            skill_name=skill.name,
            risk_level=risk_level,
        )

        return pending

    def get_pending(self) -> list[PendingSkill]:
        """Ritorna tutte le skill in attesa."""
        return list(self._pending.values())

    def get_pending_by_id(self, skill_id: str) -> Optional[PendingSkill]:
        """Ritorna skill pending per ID."""
        return self._pending.get(skill_id)

    async def approve(
        self,
        skill_id: str,
        reviewer_note: Optional[str] = None,
    ) -> Optional[PendingSkill]:
        """Approva una skill pending.

        Args:
            skill_id: ID della skill
            reviewer_note: Nota opzionale del reviewer

        Returns:
            PendingSkill approvata o None se non trovata
        """
        pending = self._pending.pop(skill_id, None)
        if not pending:
            return None

        pending.status = ApprovalStatus.APPROVED
        pending.reviewed_at = datetime.now()
        pending.reviewer_note = reviewer_note

        self._approved[skill_id] = pending

        logger.info(
            "skill_approved",
            skill_id=skill_id,
            skill_name=pending.skill.name,
        )

        if self._on_approved:
            await self._on_approved(pending)

        return pending

    async def reject(
        self,
        skill_id: str,
        reason: str = "Rejected by user",
    ) -> Optional[PendingSkill]:
        """Rifiuta una skill pending.

        Args:
            skill_id: ID della skill
            reason: Motivo del rifiuto

        Returns:
            PendingSkill rifiutata o None se non trovata
        """
        pending = self._pending.pop(skill_id, None)
        if not pending:
            return None

        pending.status = ApprovalStatus.REJECTED
        pending.reviewed_at = datetime.now()
        pending.reviewer_note = reason

        self._rejected[skill_id] = pending

        logger.info(
            "skill_rejected",
            skill_id=skill_id,
            skill_name=pending.skill.name,
            reason=reason,
        )

        if self._on_rejected:
            await self._on_rejected(pending)

        return pending

    def get_stats(self) -> dict:
        """Ritorna statistiche."""
        return {
            "pending": len(self._pending),
            "approved": len(self._approved),
            "rejected": len(self._rejected),
        }


# Singleton instance
_approval_manager: Optional[SkillApprovalManager] = None


def get_skill_approval_manager() -> SkillApprovalManager:
    """Ottiene singleton SkillApprovalManager."""
    global _approval_manager
    if _approval_manager is None:
        _approval_manager = SkillApprovalManager()
    return _approval_manager
