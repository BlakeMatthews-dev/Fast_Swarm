from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ....Database import get_session
from ..Models.governance_models import Committee, CommitteeDecision, CommitteeVote
from ..Services import governance_service

router = APIRouter(prefix="/governance", tags=["Governance"])


@router.get("/committees", response_model=list[Committee])
async def list_committees(session: AsyncSession = Depends(get_session)):
    """List all active committees."""
    return await governance_service.get_all_committees(session)


@router.get("/committees/{committee_id}", response_model=Committee)
async def get_committee(committee_id: str, session: AsyncSession = Depends(get_session)):
    """Get details of a specific committee."""
    committee = await governance_service.get_committee_by_id(session, committee_id)
    if not committee:
        raise HTTPException(status_code=404, detail="Committee not found")
    return committee


@router.get("/committees/{committee_id}/decisions", response_model=list[CommitteeDecision])
async def list_committee_decisions(committee_id: str, limit: int = 20, session: AsyncSession = Depends(get_session)):
    """Get recent consensus decisions made by this committee."""
    return await governance_service.get_recent_decisions(session, committee_id, limit)


@router.get("/committees/{committee_id}/votes", response_model=list[CommitteeVote])
async def list_committee_votes(committee_id: str, limit: int = 50, session: AsyncSession = Depends(get_session)):
    """Get individual agent votes for this committee (Raw data stream)."""
    return await governance_service.get_recent_votes(session, committee_id, limit)
