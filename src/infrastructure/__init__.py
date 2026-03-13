# Infrastructure layer - external concerns (database, APIs)
# Do not import .database or .github_api here to avoid module lock deadlocks
# when Streamlit loads pages concurrently. Import directly from submodules instead:
#   from src.infrastructure.database import init_db, ...
#   from src.infrastructure.github_api import GitHubAPI
__all__ = []
