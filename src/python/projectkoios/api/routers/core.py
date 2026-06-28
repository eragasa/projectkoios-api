from fastapi import APIRouter


def create_core_router() -> APIRouter:
    router = APIRouter(tags=["core"])

    @router.get("/")
    def read_root() -> dict[str, str]:
        return {
            "message": "Hello, Project Koios",
        }

    @router.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
        }

    return router
