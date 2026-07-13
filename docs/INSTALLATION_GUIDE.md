# MjolnirOS v1.0 Installation Guide

Install Python 3.12+ and Node.js 20+, create `.venv`, install `requirements.txt`, and run `npm install`. Start development services with `npm run backend:dev` and `npm run frontend:dev`, then launch Electron with `npm run desktop:dev`.

The desktop runtime supports Windows login startup through Settings and provides Open, Restart, Settings, and Quit tray actions. The Docker frontend is a static Nginx image exposed by Compose at `http://localhost:5173`; the backend remains at port 8000. Production packages should be signed and distributed by the Windows installer pipeline; no updater silently downloads code.
