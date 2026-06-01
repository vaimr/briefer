"""MatrixClientWrapper — async wrapper around matrix-nio AsyncClient.

T2.1.1 — Create Matrix Client Wrapper Base Class

Provides a clean, testable interface for:
  - Connection management (connect / disconnect)
  - Authentication (login)
  - Messaging (send_message)
  - File operations (download, upload)
  - Async context manager protocol
"""

from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from typing import Any, Callable, Optional

from nio import AsyncClient, UploadResponse

logger = logging.getLogger(__name__)

EventFilter = Callable[[Any], bool]


class MatrixClientWrapper:
    """Async wrapper around ``nio.AsyncClient``.

    Parameters
    ----------
    homeserver : str
        Matrix homeserver URL (e.g. ``https://matrix.example.com``).
    user : str
        Matrix user ID (e.g. ``@briefer:example.com``).
    password : str
        Matrix password. Can be empty if using access token externally.
    device_name : str
        Device name for login. Defaults to ``"briefer-bot"``.
    """

    DEFAULT_DEVICE_NAME = "briefer-bot"

    def __init__(
        self,
        homeserver: str,
        user: str,
        password: str = "",
        device_name: str = "",
    ) -> None:
        self.homeserver = homeserver
        self.user = user
        self.password = password
        self.device_name = device_name or self.DEFAULT_DEVICE_NAME
        self._client: Optional[AsyncClient] = None
        self.is_connected: bool = False
        self._filters: list[EventFilter] = []

    @property
    def client(self) -> Optional[AsyncClient]:
        """Expose the underlying AsyncClient for testing."""
        return self._client

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Create and initialise the underlying ``AsyncClient``.

        Raises
        ------
        RuntimeError
            If already connected.
        """
        if self.is_connected:
            raise RuntimeError("MatrixClientWrapper is already connected")

        self._client = AsyncClient(self.homeserver, self.user)
        self._client.set_push_encrypted_to_device(False)
        self.is_connected = True
        logger.info(
            "Matrix client connected to %s as %s",
            self.homeserver,
            self.user,
        )

    async def disconnect(self) -> None:
        """Close the underlying ``AsyncClient`` session."""
        if self._client is not None:
            await self._client.close()
        self._client = None
        self.is_connected = False
        logger.info("Matrix client disconnected")

    async def login(self, password: Optional[str] = None) -> None:
        """Authenticate using the stored (or provided) password.

        The client must be connected first.

        Raises
        ------
        RuntimeError
            If not connected.
        """
        if not self.is_connected:
            raise RuntimeError("MatrixClientWrapper is not connected — call connect() first")

        pwd = password or self.password
        if not pwd:
            raise ValueError("Password is required for login")

        await self._client.login(  # type: ignore[union-attr]
            password=pwd,
            device_name=self.device_name,
        )
        logger.info("Matrix client authenticated as %s", self.user)

    # ------------------------------------------------------------------
    # Room management
    # ------------------------------------------------------------------

    def get_room(self, room_id: str) -> Optional[Any]:
        """Return the ``Room`` object for *room_id*, or ``None``.

        Raises
        ------
        RuntimeError
            If not connected.
        ValueError
            If *room_id* is empty.
        """
        if not room_id:
            raise ValueError("room_id must not be empty")
        if not self.is_connected:
            raise RuntimeError("MatrixClientWrapper is not connected")

        return self._client.rooms.get(room_id)  # type: ignore[union-attr]

    async def join_room(self, alias_or_id: str) -> None:
        """Join a room by its ID or alias.

        Raises
        ------
        RuntimeError
            If not connected.
        ValueError
            If *alias_or_id* is empty.
        """
        if not alias_or_id:
            raise ValueError("alias_or_id must not be empty")
        if not self.is_connected:
            raise RuntimeError("MatrixClientWrapper is not connected")

        await self._client.join_room(alias_or_id)  # type: ignore[union-attr]
        logger.info("Joined room %s", alias_or_id)

    def list_rooms(self) -> list[Any]:
        """Return a list of all joined ``Room`` objects.

        Raises
        ------
        RuntimeError
            If not connected.
        """
        if not self.is_connected:
            raise RuntimeError("MatrixClientWrapper is not connected")

        return list(self._client.rooms.values())  # type: ignore[union-attr]

    async def send_text(self, room_id: str, body: str) -> None:
        """Send a plain-text message to *room_id*.

        Raises
        ------
        RuntimeError
            If not connected.
        ValueError
            If *room_id* or *body* is empty.
        """
        if not room_id:
            raise ValueError("room_id must not be empty")
        if not body:
            raise ValueError("body must not be empty")
        if not self.is_connected:
            raise RuntimeError("MatrixClientWrapper is not connected")

        await self._client.room_send(  # type: ignore[union-attr]
            room_id,
            "m.room.message",
            {
                "msgtype": "m.text",
                "body": body,
            },
        )
        logger.debug("Text message sent to %s", room_id)

    async def send_image(
        self,
        room_id: str,
        data: bytes,
        filename: str,
    ) -> str:
        """Upload an image and send it to *room_id*.

        Returns the MXC URI of the uploaded image.

        Raises
        ------
        RuntimeError
            If not connected.
        ValueError
            If *room_id*, *data*, or *filename* is empty.
        """
        if not room_id:
            raise ValueError("room_id must not be empty")
        if not data:
            raise ValueError("data must not be empty")
        if not filename:
            raise ValueError("filename must not be empty")
        if not self.is_connected:
            raise RuntimeError("MatrixClientWrapper is not connected")

        # MIME type from filename extension
        ext = filename.rsplit(".", 1)[-1].lower()
        mime_map: dict[str, str] = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "webp": "image/webp",
            "svg": "image/svg+xml",
        }
        mime_type = mime_map.get(ext, "image/png")

        resp = await self._client.upload(  # type: ignore[union-attr]
            BytesIO(data),
            content_type=mime_type,
        )
        mxc_uri = resp.content_uri

        await self._client.room_send(  # type: ignore[union-attr]
            room_id,
            "m.room.message",
            {
                "msgtype": "m.image",
                "body": filename,
                "info": {
                    "mimetype": mime_type,
                    "size": len(data),
                },
                "url": mxc_uri,
            },
        )
        logger.debug("Image sent to %s, mxc=%s", room_id, mxc_uri)
        return mxc_uri

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    def add_filter(self, filter_func: EventFilter) -> None:
        """Add an event filter to the filter chain.

        Filters are applied sequentially. If any filter returns ``False``,
        the event is rejected and the handler is not called.

        Raises
        ------
        TypeError
            If *filter_func* is not callable.
        """
        if not callable(filter_func):
            raise TypeError("filter_func must be callable")
        self._filters.append(filter_func)
        logger.debug("Filter added, total=%d", len(self._filters))

    def _apply_filters(self, event: Any) -> bool:
        """Apply all filters to *event*.

        Returns ``True`` if all filters pass, ``False`` otherwise.
        """
        for f in self._filters:
            if not f(event):
                logger.debug("Filter rejected event: %s", f)
                return False
        return True

    def handle_message(self, event: Any) -> Any:
        """Extract the message body from a Matrix event.

        Parameters
        ----------
        event : Any
            A Matrix event object (e.g. ``MatrixEvent``).

        Returns
        -------
        Any
            The event body, or ``None`` if not present.
        """
        return getattr(event, "body", None)

    async def process_event(
        self,
        event: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """Process an event through filters and handler.

        Filters are applied first. If any filter returns ``False``,
        the handler is not called and ``None`` is returned.

        Parameters
        ----------
        event : Any
            The Matrix event to process.
        handler : Callable[[Any], Any]
            The handler function to call if all filters pass.

        Returns
        -------
        Any
            The handler return value, or ``None`` if rejected.
        """
        if not self._apply_filters(event):
            return None

        if asyncio.iscoroutinefunction(handler):
            return await handler(event)
        return handler(event)

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    async def send_message(
        self,
        room_id: str,
        body: str,
    ) -> None:
        """Send a text message to *room_id*.

        Raises
        ------
        RuntimeError
            If not connected.
        ValueError
            If *room_id* or *body* is empty.
        """
        if not room_id:
            raise ValueError("room_id must not be empty")
        if not body:
            raise ValueError("body must not be empty")
        if not self.is_connected:
            raise RuntimeError("MatrixClientWrapper is not connected")

        await self._client.room_send(  # type: ignore[union-attr]
            room_id,
            "m.room.message",
            {
                "msgtype": "m.text",
                "body": body,
            },
        )
        logger.debug("Message sent to %s", room_id)

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    async def download(self, url: str) -> bytes:
        """Download file content from *url*.

        Raises
        ------
        RuntimeError
            If not connected.
        ValueError
            If *url* is empty.
        """
        if not url:
            raise ValueError("url must not be empty")
        if not self.is_connected:
            raise RuntimeError("MatrixClientWrapper is not connected")

        response = await self._client.download(url)  # type: ignore[union-attr]
        return response.body

    async def upload(
        self,
        data: bytes,
        mime_type: str,
    ) -> str:
        """Upload *data* with *mime_type* and return the MXC URI.

        Raises
        ------
        RuntimeError
            If not connected.
        ValueError
            If *data* or *mime_type* is empty.
        """
        if not data:
            raise ValueError("data must not be empty")
        if not mime_type:
            raise ValueError("mime_type must not be empty")
        if not self.is_connected:
            raise RuntimeError("MatrixClientWrapper is not connected")

        file_obj = BytesIO(data)
        resp: UploadResponse = await self._client.upload(  # type: ignore[union-attr]
            file_obj,
            content_type=mime_type,
        )
        logger.debug("Uploaded file, content_uri=%s", resp.content_uri)
        return resp.content_uri

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "MatrixClientWrapper":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> None:
        await self.disconnect()
