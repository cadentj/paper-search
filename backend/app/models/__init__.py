from app.models.base import Base
from app.models.filter import FilterPayload, Filter, SQLAFilter
from app.models.job import Job, SQLAJob
from app.models.onboarding_extraction import (
    OnboardingExtraction,
    ProposedFilter,
    SQLAOnboardingExtraction,
)
from paper_search_core.models.paper import Paper, SQLAPaper
from app.models.search_run import SQLASearchRun, SearchRun
from app.models.paper_match import SQLAPaperMatch
from app.models.paper_match_feedback import SQLAPaperMatchFeedback
from app.models.idea_map import IdeaMap, SQLAIdeaMap
from app.models.app_setting import SQLAAppSetting
from app.models.paper_note import SQLAPaperNote
from app.models.research_profile_import import SQLAResearchProfileImport

__all__ = [
    "Base",
    "FilterPayload",
    "Filter",
    "IdeaMap",
    "Job",
    "OnboardingExtraction",
    "Paper",
    "ProposedFilter",
    "SQLAAppSetting",
    "SQLAFilter",
    "SQLAIdeaMap",
    "SQLAJob",
    "SQLAOnboardingExtraction",
    "SQLAPaper",
    "SQLAPaperMatch",
    "SQLAPaperMatchFeedback",
    "SQLAPaperNote",
    "SQLAResearchProfileImport",
    "SQLASearchRun",
    "SearchRun",
]
