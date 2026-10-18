"""Routes des playlists de l'utilisateur connecté : lecture (avec les enchaînements) et modification."""

from dataclasses import asdict
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, StringConstraints

from app.adapters.playlist_repository import PlaylistRepository
from app.adapters.spotify_provider import SpotifyProvider
from app.api.deps import (
    get_current_user_id,
    get_playlist_editor,
    get_playlist_exporter,
    get_playlist_reorderer,
    get_playlist_repository,
    get_spotify_connection,
    get_spotify_provider,
)
from app.api.tracks import DEFAULT_BPM_TOLERANCE, CatalogTrack
from app.api.transitions import RatingOut, Transition
from app.domain.reorder import OrderQuality
from app.services.playlist_editor import PlaylistEditor
from app.services.playlist_export import PlaylistExporter
from app.services.playlist_reorder import PlaylistReorderer
from app.services.spotify_connection import SpotifyConnection

router = APIRouter(prefix="/playlists", tags=["playlists"])

CurrentUser = Annotated[UUID, Depends(get_current_user_id)]


Playlists = Annotated[PlaylistRepository, Depends(get_playlist_repository)]
Editor = Annotated[PlaylistEditor, Depends(get_playlist_editor)]
PlaylistName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class PlaylistSummary(BaseModel):
    """Une playlist ; source_provider null = créée ici, sinon importée (lecture seule)."""

    id: UUID
    name: str
    source_provider: str | None
    track_count: int
    updated_at: datetime


class PlaylistItem(BaseModel):
    """Un morceau de la playlist ; transition_to_next null = dernier morceau, ou l'un des deux non analysé."""

    item_id: int
    position: int
    track: CatalogTrack
    transition_to_next: Transition | None
    my_rating: RatingOut | None


class SpotifyExport(BaseModel):
    """Dernier export de la playlist vers Spotify."""

    url: str
    exported_at: datetime


class PlaylistDetail(PlaylistSummary):
    """Une playlist avec ses morceaux dans l'ordre ; spotify_export null = jamais exportée."""

    items: list[PlaylistItem]
    spotify_export: SpotifyExport | None


@router.get("")
async def list_playlists(playlists: Playlists, user_id: CurrentUser) -> list[PlaylistSummary]:
    """Mes playlists (créées ici ou importées), les plus récemment modifiées d'abord."""
    return [PlaylistSummary(**asdict(p)) for p in await playlists.list_for_owner(user_id)]


@router.get("/{playlist_id}")
async def get_playlist(
    playlist_id: UUID,
    playlists: Playlists,
    user_id: CurrentUser,
    spotify: Annotated[SpotifyProvider, Depends(get_spotify_provider)],
) -> PlaylistDetail:
    """Une de mes playlists, avec l'enchaînement entre chaque morceau ; 404 si elle n'est pas à moi."""
    playlist = await playlists.get_for_owner(user_id, playlist_id)
    if playlist is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playlist inconnue")
    items = await playlists.items_with_transitions(user_id, playlist_id, DEFAULT_BPM_TOLERANCE)
    export = await playlists.get_export(playlist_id, spotify.name)
    return PlaylistDetail(
        **asdict(playlist),
        items=[PlaylistItem(**asdict(i)) for i in items],
        spotify_export=(
            SpotifyExport(
                url=spotify.playlist_url(export.external_playlist_id), exported_at=export.last_synced_at
            )
            if export
            else None
        ),
    )


class PlaylistNameIn(BaseModel):
    """Nom d'une playlist (espaces de début et de fin retirés, 1 à 100 caractères)."""

    name: PlaylistName


class TrackToAdd(BaseModel):
    """Morceau à ajouter en fin de playlist, ou à `position` (0 = en tête ; au-delà de la fin = en fin)."""

    track_id: UUID
    position: Annotated[int, Field(ge=0)] | None = None


class AddedItem(BaseModel):
    """Élément ajouté : son identifiant et sa position dans la playlist."""

    item_id: int
    position: int


class TracksToInsert(BaseModel):
    """Morceaux à insérer ensemble, dans l'ordre, à partir de `position` (un chemin entre deux morceaux)."""

    track_ids: Annotated[list[UUID], Field(min_length=1, max_length=20)]
    position: Annotated[int, Field(ge=0)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_playlist(body: PlaylistNameIn, editor: Editor, user_id: CurrentUser) -> PlaylistSummary:
    """Crée une playlist vide."""
    return PlaylistSummary(**asdict(await editor.create(user_id, body.name)))


@router.patch("/{playlist_id}")
async def rename_playlist(
    playlist_id: UUID, body: PlaylistNameIn, editor: Editor, user_id: CurrentUser
) -> PlaylistSummary:
    """Renomme une de mes playlists ; 409 si elle est importée."""
    return PlaylistSummary(**asdict(await editor.rename(user_id, playlist_id, body.name)))


@router.delete("/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playlist(playlist_id: UUID, editor: Editor, user_id: CurrentUser) -> Response:
    """Supprime une de mes playlists (les morceaux restent dans le catalogue)."""
    await editor.delete(user_id, playlist_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{playlist_id}/items", status_code=status.HTTP_201_CREATED)
async def add_track(playlist_id: UUID, body: TrackToAdd, editor: Editor, user_id: CurrentUser) -> AddedItem:
    """Ajoute un morceau (en fin, ou à `position`) ; 409 si playlist importée, 404 si morceau inconnu."""
    item_id, position = await editor.add_track(user_id, playlist_id, body.track_id, body.position)
    return AddedItem(item_id=item_id, position=position)


@router.post("/{playlist_id}/items/batch", status_code=status.HTTP_201_CREATED)
async def insert_tracks(
    playlist_id: UUID, body: TracksToInsert, editor: Editor, user_id: CurrentUser
) -> list[AddedItem]:
    """Insère plusieurs morceaux d'un coup (tout ou rien) ; 409 si importée, 404 si morceau inconnu."""
    added = await editor.insert_tracks(user_id, playlist_id, body.track_ids, body.position)
    return [AddedItem(item_id=item_id, position=position) for item_id, position in added]


@router.post("/{playlist_id}/copy", status_code=status.HTTP_201_CREATED)
async def copy_playlist(playlist_id: UUID, editor: Editor, user_id: CurrentUser) -> PlaylistSummary:
    """Duplique une de mes playlists (même importée) en une playlist modifiable « X (copie) »."""
    return PlaylistSummary(**asdict(await editor.copy(user_id, playlist_id)))


class NewOrder(BaseModel):
    """Tous les éléments de la playlist (item_id), dans le nouvel ordre."""

    item_ids: list[int]


class OrderQualityOut(BaseModel):
    """Bilan d'un ordre : enchaînements refusés et score moyen par enchaînement (morceaux analysés)."""

    refused: int
    mean_score: float


class OrderStep(BaseModel):
    """Enchaînement entre deux morceaux consécutifs de l'ordre proposé ; transition null = refusé."""

    transition: Transition | None
    score: float | None


class OrderProposal(BaseModel):
    """Ordre proposé (à appliquer avec PUT …/order) et bilan avant / après ; rien n'est encore modifié."""

    item_ids: list[int]
    before: OrderQualityOut
    after: OrderQualityOut
    unanalysed: int
    steps: list[OrderStep]


def _quality(quality: OrderQuality, transitions: int) -> OrderQualityOut:
    """Bilan affiché : refus et score moyen par enchaînement (un refusé compte 0)."""
    return OrderQualityOut(
        refused=quality.refused,
        mean_score=round(quality.total_score / transitions, 3) if transitions else 0.0,
    )


@router.get("/{playlist_id}/order/proposal")
async def propose_order(
    playlist_id: UUID,
    reorderer: Annotated[PlaylistReorderer, Depends(get_playlist_reorderer)],
    user_id: CurrentUser,
) -> OrderProposal:
    """Propose l'ordre qui enchaîne le mieux (ouverture comprise) ; 404 si pas à moi, 409 si importée."""
    proposal = await reorderer.propose(user_id, playlist_id, DEFAULT_BPM_TOLERANCE)
    transitions = len(proposal.steps)
    return OrderProposal(
        item_ids=proposal.item_ids,
        before=_quality(proposal.before, transitions),
        after=_quality(proposal.after, transitions),
        unanalysed=proposal.unanalysed,
        steps=[
            OrderStep(transition=Transition(**asdict(s.transition)), score=s.score)
            if s is not None
            else OrderStep(transition=None, score=None)
            for s in proposal.steps
        ],
    )


@router.put("/{playlist_id}/order", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_playlist(
    playlist_id: UUID, body: NewOrder, editor: Editor, user_id: CurrentUser
) -> Response:
    """Change l'ordre des morceaux ; 422 si la liste ne correspond plus au contenu (page à recharger)."""
    await editor.reorder(user_id, playlist_id, body.item_ids)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{playlist_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item(playlist_id: UUID, item_id: int, editor: Editor, user_id: CurrentUser) -> Response:
    """Retire un morceau de la playlist ; 404 s'il n'y est pas."""
    await editor.remove_item(user_id, playlist_id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ExportOutcome(BaseModel):
    """Bilan d'un export : created = nouvelle playlist chez Spotify (sinon : mise à jour de la précédente)."""

    url: str
    created: bool
    exported: int
    skipped: int
    exported_at: datetime


@router.post("/{playlist_id}/export/spotify")
async def export_to_spotify(
    playlist_id: UUID,
    user_id: CurrentUser,
    connection: Annotated[SpotifyConnection, Depends(get_spotify_connection)],
    exporter: Annotated[PlaylistExporter, Depends(get_playlist_exporter)],
) -> ExportOutcome:
    """Exporte la playlist vers Spotify (privée) ou met à jour l'export précédent ; 409 si importée."""
    result = await exporter.export(user_id, playlist_id, await connection.access_token(user_id))
    return ExportOutcome(
        url=result.url,
        created=result.created,
        exported=result.exported,
        skipped=result.skipped,
        exported_at=result.exported_at,
    )
