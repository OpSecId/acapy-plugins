"""Module for handling pending webvh dids."""

import logging
from typing import Any, Optional

from acapy_agent.core.profile import Profile
from .states import WitnessingState

LOGGER = logging.getLogger(__name__)


class BasePendingRecord:
    """Base class to manage pending witness requests."""

    RECORD_TYPE = "generic_record"
    RECORD_TOPIC = "generic-record"
    EVENT_NAMESPACE: str = "acapy::record"
    instance = None

    def __new__(cls, *args, **kwargs):
        """Create a new instance of the class."""
        if cls.instance is None:
            cls.instance = super().__new__(cls)
        return cls.instance

    async def get_pending_records(self, profile: Profile) -> list:
        """Get all pending records."""
        async with profile.session() as session:
            entries = await session.handle.fetch_all(self.RECORD_TYPE)
        # Filter out legacy index record if present (value_json was list of ids)
        return [
            entry.value_json
            for entry in list(entries)
            if isinstance(entry.value_json, dict)
        ]

    async def get_pending_record(self, profile: Profile, record_id: str) -> set:
        """Get a pending record given a record_id."""
        async with profile.session() as session:
            entry = await session.handle.fetch(self.RECORD_TYPE, record_id)
        return entry.value_json, entry.tags.get("connection_id")

    async def remove_pending_record(self, profile: Profile, record_id: str) -> set:
        """Remove a pending record given a record_id."""
        async with profile.session() as session:
            await session.handle.remove(self.RECORD_TYPE, record_id)

        return {"status": "success", "message": f"Removed {self.RECORD_TYPE}."}

    async def save_pending_record(
        self,
        profile: Profile,
        scid: str,
        record: dict,
        record_id: str,
        connection_id: str = "",
        role: str = None,
    ) -> set:
        """Save a pending record given a scid.
        
        Args:
            profile: The profile to use
            scid: The short circuit identifier
            record: The record document to save
            record_id: The unique record identifier
            connection_id: The connection ID (empty for self-witnessing)
            role: The role of the agent saving ("controller", "witness", or "self-witness")
        """
        role_value = role or "controller"  # Default to controller for backwards compatibility
        pending_record = {
            "record_id": record_id,
            "record_type": self.RECORD_TYPE,
            "record": record,
            "state": WitnessingState.PENDING.value,
            "scid": scid,
            "role": role_value,
        }
        async with profile.session() as session:
            await session.handle.insert(
                self.RECORD_TYPE,
                record_id,
                value_json=pending_record,
                tags={"connection_id": connection_id or "", "role": role_value},
            )
        await self.emit_event(profile, pending_record)

    async def emit_event(self, profile: Profile, payload: Optional[Any] = None):
        """Emit an event.

        Args:
            profile: The profile to use
            payload: The event payload
        """

        if not self.RECORD_TYPE:
            return

        topic = f"{self.EVENT_NAMESPACE}::{self.RECORD_TYPE}"

        if not payload:
            payload = self.serialize()

        async with profile.session() as session:
            await session.emit_event(topic, payload, True)
