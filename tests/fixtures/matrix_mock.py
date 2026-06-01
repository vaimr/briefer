"""Mock Matrix AsyncClient for testing.

Provides a fake Matrix client that mimics the interface of nio.AsyncClient
used by bot and worker modules (login, sync_forever, add_event_callback,
room_send, download, upload, sync_once).
"""

from unittest.mock import AsyncMock, MagicMock


class FakeUploadResponse:
    """Fake nio.UploadResponse."""

    def __init__(self, content_uri: str = "mxc://briefer/test.pdf"):
        self.content_uri = content_uri


class FakeMatrixClient:
    """Fake Matrix AsyncClient for testing.

    Mimics nio.AsyncClient interface for:
    - login (password-based auth)
    - sync_forever / sync_once (event loop)
    - add_event_callback (event routing)
    - room_send (sending messages)
    - download (file download)
    - upload (file upload)
    """

    def __init__(self, homeserver: str = "https://matrix.example.com", user: str = "@bot:example.com"):
        self.homeserver = homeserver
        self.user_id = user
        self.access_token: str | None = None
        self._callbacks: list[tuple] = []
        self._sent_messages: list[dict] = []
        self._uploaded: list[dict] = []
        self._sync_count = 0
        self._logged_in = False

    async def login(self, password: str = "test", device_name: str = "test-device") -> None:
        """Simulate login."""
        self.access_token = "fake_token"
        self._logged_in = True

    async def sync_forever(self, timeout: int = 30000) -> None:
        """Simulate infinite sync loop.

        In tests, this should be mocked or awaited with a timeout.
        """
        while True:
            self._sync_count += 1
            await asyncio.sleep(0)

    async def sync_once(self, timeout: int = 5000) -> None:
        """Simulate a single sync."""
        self._sync_count += 1

    def add_event_callback(self, callback, event_types) -> None:
        """Register an event callback."""
        self._callbacks.append((callback, event_types))

    async def room_send(self, room_id: str, msgtype: str, content: dict) -> None:
        """Simulate sending a room message."""
        self._sent_messages.append({
            "room_id": room_id,
            "msgtype": msgtype,
            "content": content,
        })

    async def download(self, url) -> MagicMock:
        """Simulate downloading a file."""
        mock = MagicMock()
        mock.body = b"fake audio data"
        return mock

    async def upload(self, file_obj, content_type: str = "application/octet-stream") -> tuple:
        """Simulate uploading a file."""
        self._uploaded.append({
            "content_type": content_type,
        })
        response = FakeUploadResponse()
        return response, None

    def get_sent_messages(self) -> list[dict]:
        """Return all sent messages."""
        return list(self._sent_messages)

    def get_uploaded_files(self) -> list[dict]:
        """Return all uploaded files."""
        return list(self._uploaded)

    def get_callbacks(self) -> list[tuple]:
        """Return registered callbacks."""
        return list(self._callbacks)

    def reset(self) -> None:
        """Reset all state."""
        self._sent_messages.clear()
        self._uploaded.clear()
        self._sync_count = 0


def mock_matrix_client(
    homeserver: str = "https://matrix.example.com",
    user: str = "@bot:example.com",
    access_token: str = "fake_token",
    password: str = "test",
):
    """Factory fixture to create a FakeMatrixClient.

    Example:
        client = mock_matrix_client()
        assert client.user_id == "@bot:example.com"
    """
    client = FakeMatrixClient(homeserver=homeserver, user=user)
    if access_token:
        client.access_token = access_token
    return client
