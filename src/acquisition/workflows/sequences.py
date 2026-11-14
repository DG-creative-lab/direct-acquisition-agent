"""Explicit composition of campaign proposals and the synthetic engagement lifecycle."""

from dataclasses import dataclass

from acquisition.campaigns import SequenceCampaigns
from acquisition.engagements import EngagementSimulator
from acquisition.reviews import SequenceReviews


@dataclass(frozen=True)
class SequenceSimulation:
    campaigns: SequenceCampaigns
    engagements: EngagementSimulator
    reviews: SequenceReviews
