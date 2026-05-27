"""
Announcements endpoints for Mergington High School API.

Active announcements are public; create/update/delete require teacher authentication.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional, List
from datetime import date, datetime
from bson import ObjectId
from pydantic import BaseModel

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementCreate(BaseModel):
    message: str
    start_date: Optional[str] = None   # ISO date YYYY-MM-DD (optional)
    expiry_date: str                    # ISO date YYYY-MM-DD (required)


class AnnouncementUpdate(BaseModel):
    message: str
    start_date: Optional[str] = None
    expiry_date: str


def _serialize(ann: dict) -> dict:
    """Convert MongoDB document to JSON-serialisable dict."""
    ann["id"] = str(ann.pop("_id"))
    return ann


def _verify_teacher(teacher_username: str) -> dict:
    """Raise 401 if username is not a known teacher."""
    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    return teacher


def _validate_dates(start_date: Optional[str], expiry_date: str) -> None:
    """Validate ISO date strings and logical ordering."""
    try:
        expiry = date.fromisoformat(expiry_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Data de expiração inválida (use YYYY-MM-DD)")

    if start_date:
        try:
            start = date.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Data de início inválida (use YYYY-MM-DD)")
        if start > expiry:
            raise HTTPException(
                status_code=400,
                detail="A data de início não pode ser posterior à data de expiração"
            )


@router.get("", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Return announcements visible today (public endpoint)."""
    today = date.today().isoformat()
    query = {
        "expiry_date": {"$gte": today},
        "$or": [
            {"start_date": None},
            {"start_date": {"$lte": today}}
        ]
    }
    return [_serialize(ann) for ann in announcements_collection.find(query).sort("created_at", 1)]


@router.get("/all", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: str = Query(...)) -> List[Dict[str, Any]]:
    """Return all announcements regardless of dates — requires teacher auth."""
    _verify_teacher(teacher_username)
    return [_serialize(ann) for ann in announcements_collection.find().sort("expiry_date", 1)]


@router.post("", response_model=Dict[str, Any])
def create_announcement(
    announcement: AnnouncementCreate,
    teacher_username: str = Query(...)
) -> Dict[str, Any]:
    """Create a new announcement — requires teacher auth."""
    _verify_teacher(teacher_username)
    _validate_dates(announcement.start_date, announcement.expiry_date)

    message = announcement.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="A mensagem não pode estar vazia")

    doc = {
        "message": message,
        "start_date": announcement.start_date or None,
        "expiry_date": announcement.expiry_date,
        "created_by": teacher_username,
        "created_at": datetime.utcnow().isoformat()
    }

    result = announcements_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return doc


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    announcement: AnnouncementUpdate,
    teacher_username: str = Query(...)
) -> Dict[str, Any]:
    """Update an existing announcement — requires teacher auth."""
    _verify_teacher(teacher_username)
    _validate_dates(announcement.start_date, announcement.expiry_date)

    try:
        obj_id = ObjectId(announcement_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de anúncio inválido")

    if not announcements_collection.find_one({"_id": obj_id}):
        raise HTTPException(status_code=404, detail="Anúncio não encontrado")

    message = announcement.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="A mensagem não pode estar vazia")

    announcements_collection.update_one(
        {"_id": obj_id},
        {"$set": {
            "message": message,
            "start_date": announcement.start_date or None,
            "expiry_date": announcement.expiry_date
        }}
    )

    updated = announcements_collection.find_one({"_id": obj_id})
    return _serialize(updated)


@router.delete("/{announcement_id}", response_model=Dict[str, Any])
def delete_announcement(
    announcement_id: str,
    teacher_username: str = Query(...)
) -> Dict[str, Any]:
    """Delete an announcement — requires teacher auth."""
    _verify_teacher(teacher_username)

    try:
        obj_id = ObjectId(announcement_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de anúncio inválido")

    result = announcements_collection.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Anúncio não encontrado")

    return {"message": "Anúncio excluído com sucesso"}
