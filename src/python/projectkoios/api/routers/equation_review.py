"""FastAPI factory boundary for the equation-review capability."""

from fastapi import APIRouter
from projectkoios.api.equation_review import EquationReviewRepository
from projectkoios.api.equation_review.router import build_equation_review_router


def create_equation_review_router(
    repository: EquationReviewRepository,
) -> APIRouter:
    return build_equation_review_router(repository)
