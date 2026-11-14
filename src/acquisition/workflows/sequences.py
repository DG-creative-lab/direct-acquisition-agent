"""Explicit composition of campaign proposals and the synthetic engagement lifecycle."""

from dataclasses import dataclass

from acquisition.campaigns import SequenceCampaigns
from acquisition.engagements import EngagementSimulator


@dataclass(frozen=True)
class SequenceSimulation:
    campaigns: SequenceCampaigns
    engagements: EngagementSimulator
