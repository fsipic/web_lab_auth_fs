from app import db
from sqlalchemy.dialects.postgresql import UUID
import uuid

class Ticket(db.Model):
    __tablename__ = 'tickets'

    ticket_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vat_id = db.Column(db.String(20), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    time_created = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())
