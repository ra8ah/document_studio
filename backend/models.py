from datetime import datetime, timezone
from typing import Any, List, Optional
from bson import ObjectId
from pydantic import BaseModel, Field, BeforeValidator, ConfigDict
from typing_extensions import Annotated


def _validate_object_id(v: Any) -> str:
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, str):
        return v
    raise ValueError("Invalid ObjectId")


PyObjectId = Annotated[str, BeforeValidator(_validate_object_id)]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True, extra="ignore")
    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    @classmethod
    def from_mongo(cls, doc: dict):
        if not doc:
            return None
        return cls(**doc)

    def to_mongo(self) -> dict:
        data = self.model_dump(by_alias=True, exclude_none=True)
        data.pop("_id", None)
        data.pop("id", None)
        return data


# ---------- Business Profile ----------
class BusinessProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    agency_name: str = ""
    legal_name: str = ""
    tagline: str = ""
    logo_url: str = ""
    address: str = ""
    email: str = ""
    phone: str = ""
    website: str = ""
    tax_ids: str = ""  # GST / VAT / GSTIN
    bank_name: str = ""
    bank_account: str = ""
    ifsc: str = ""
    swift: str = ""
    upi: str = ""
    payment_links: str = ""
    default_currency: str = "INR"
    default_terms: str = "Payment due within 14 days of the issue date."
    default_notes: str = ""
    prefixes: dict = Field(default_factory=dict)


# ---------- Client ----------
class ClientIn(BaseModel):
    name: str = ""
    company: str = ""
    address: str = ""
    email: str = ""
    phone: str = ""
    tax_id: str = ""
    currency: str = "INR"
    notes: str = ""


# ---------- Line items / packages ----------
class LineItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    description: str = "New service"
    sub: str = ""
    qty: float = 1
    rate: float = 0


class PackageIn(BaseModel):
    description: str = ""
    sub: str = ""
    qty: float = 1
    rate: float = 0


# ---------- Documents ----------
class DocumentIn(BaseModel):
    type: str
    client_id: Optional[str] = None
    theme: str = "light"
    currency: Optional[str] = None
    title: Optional[str] = None


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    theme: Optional[str] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    client_id: Optional[str] = None
    data: Optional[dict] = None
    line_items: Optional[List[LineItem]] = None
    discount: Optional[dict] = None
    tax: Optional[dict] = None
    recurring: Optional[dict] = None
