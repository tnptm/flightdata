import httpx
from datetime import datetime, timedelta
import json
# import os


class TokenInitialization:
    """Initializes the TokenManager with credentials from a JSON file."""

    def __init__(self, credentials_file: str):
        with open(credentials_file, "r") as f:
            creds = json.load(f)
        self.client_id = creds["clientId"]
        self.client_secret = creds["clientSecret"]


# TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
# CLIENT_ID = "your_client_id"
# CLIENT_SECRET = "your_client_secret"

# How many seconds before expiry to proactively refresh the token.
TOKEN_REFRESH_MARGIN = 30


class TokenManager:
    def __init__(self, token_url: str, credentials: TokenInitialization):
        self.token = None
        self.expires_at = None
        self.credentials = credentials
        self.token_url = token_url

    def get_token(self):
        """Return a valid access token, refreshing automatically if needed."""
        if self.token and self.expires_at and datetime.now() < self.expires_at:
            return self.token
        return self._refresh()

    def _refresh(self):
        """Fetch a new access token from the OpenSky authentication server."""
        r = httpx.post(
            self.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.credentials.client_id,
                "client_secret": self.credentials.client_secret,
            },
        )
        r.raise_for_status()

        data = r.json()
        self.token = data["access_token"]
        expires_in = data.get("expires_in", 1800)
        self.expires_at = datetime.now() + timedelta(
            seconds=expires_in - TOKEN_REFRESH_MARGIN
        )
        return self.token

    def headers(self):
        """Return request headers with a valid Bearer token."""
        return {"Authorization": f"Bearer {self.get_token()}"}


if __name__ == "__main__":
    # Create a single shared instance for your script.
    token_creds = TokenInitialization("token_credentials.json")
    tokens = TokenManager(
        token_url="https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
        credentials=token_creds,
    )

    # Use it for any API call - the token is refreshed automatically.
    response = httpx.get(
        "https://opensky-network.org/api/states/all",
        headers=tokens.headers(),
    )
    print(response.json())
