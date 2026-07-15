# Productivity Plugins

The Plugin System provides four isolated productivity plugins: Gmail, Google Calendar, Notion, and Google Drive. Their manifests use semantic version `1.0.0` and declare only the capability permissions needed for their provider.

## OAuth Setup

Create Google and Notion OAuth applications, add the loopback redirect URIs from `.env.example`, and put the client credentials only in a local `.env` file. Google credentials are shared by Gmail, Calendar, and Drive to avoid duplicate account connections. Use the dashboard **Productivity** view to start consent.

The authorization state is single-use. Tokens are encrypted with the current Windows account's DPAPI key in `database/productivity/oauth-tokens.dpapi`; the API response models deliberately omit access and refresh tokens. Google refresh tokens are used automatically when access expires. A provider that cannot refresh requires the user to reconnect.

## Safety and Auditability

The Gmail endpoint saves a draft locally and cannot send it unless the caller sends `{"confirmed": true}` to that draft's send endpoint. Google Drive deletion follows the same confirmation contract. Connection, disconnection, token-refresh, draft, send, and deletion events are structured-log audit events; credentials and message bodies are excluded.

Calendar creation accepts ISO-8601 timestamps plus an IANA timezone, rejects invalid ranges, and checks the requested window for existing events before creating a new one. Provider failures are translated to safe messages rather than returning provider credential details.
