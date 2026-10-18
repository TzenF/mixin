"""Routes des notes de transitions : je note un enchaînement A → B de 1 à 5 (sans effet sur le score)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, StringConstraints

from app.adapters.rating_repository import RatingRepository, RatingRow
from app.adapters.track_repository import TrackRepository
from app.api.deps import get_current_user_id, get_rating_repository, get_track_repository

router = APIRouter(prefix="/transitions", tags=["transitions"])

CurrentUser = Annotated[UUID, Depends(get_current_user_id)]
Ratings = Annotated[RatingRepository, Depends(get_rating_repository)]
Tracks = Annotated[TrackRepository, Depends(get_track_repository)]
Comment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class RatingIn(BaseModel):
    """Ma note (1 à 5) et un commentaire facultatif (vide = pas de commentaire)."""

    rating: Annotated[int, Field(ge=1, le=5)]
    comment: Comment | None = None


class RatingOut(BaseModel):
    """Ma note d'un enchaînement."""

    rating: int
    comment: str | None


class Transition(BaseModel):
    """Enchaînement d'un morceau vers un autre ; key_move null = tonalité incompatible (voir key_distance)."""

    key_move: str | None
    key_distance: int
    half_double: bool
    bpm_diff: float
    bpm_change: float
    tempo_ok: bool
    same_mode: bool
    compatible: bool


class RatingCount(BaseModel):
    """Nombre d'enchaînements que j'ai notés."""

    count: int


async def _check_pair(tracks: TrackRepository, from_id: UUID, to_id: UUID) -> None:
    """422 si A = B ; 404 si l'un des deux morceaux n'existe pas."""
    if from_id == to_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Un morceau ne s'enchaîne pas avec lui-même"
        )
    for track_id in (from_id, to_id):
        if not await tracks.exists(track_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Morceau inconnu")


@router.put("/{from_id}/{to_id}/rating")
async def rate_transition(
    from_id: UUID, to_id: UUID, body: RatingIn, ratings: Ratings, tracks: Tracks, user_id: CurrentUser
) -> RatingOut:
    """Note l'enchaînement de A vers B (remplace ma note précédente)."""
    await _check_pair(tracks, from_id, to_id)
    rating = RatingRow(rating=body.rating, comment=body.comment or None)
    await ratings.save(user_id, from_id, to_id, rating)
    return RatingOut(rating=rating.rating, comment=rating.comment)


@router.delete("/{from_id}/{to_id}/rating", status_code=status.HTTP_204_NO_CONTENT)
async def unrate_transition(from_id: UUID, to_id: UUID, ratings: Ratings, user_id: CurrentUser) -> Response:
    """Efface ma note de l'enchaînement de A vers B (sans effet s'il n'y en a pas)."""
    await ratings.delete(user_id, from_id, to_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/ratings/count")
async def count_ratings(ratings: Ratings, user_id: CurrentUser) -> RatingCount:
    """Combien d'enchaînements j'ai notés (il en faut quelques dizaines avant de régler le score)."""
    return RatingCount(count=await ratings.count(user_id))
