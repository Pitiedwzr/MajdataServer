from app.routers.account import router as account_router
from app.routers.maichart import router as maichart_router
from app.routers.score import router as score_router
from app.routers.collection import router as collection_router
from app.routers.interaction import router as interaction_router
from app.routers.machine_persist import router as machine_persist_router
from app.routers.stats import router as stats_router
from app.routers.utils import router as utils_router

__all__ = [
    "account_router",
    "maichart_router",
    "score_router",
    "collection_router",
    "interaction_router",
    "machine_persist_router",
    "stats_router",
    "utils_router",
]
