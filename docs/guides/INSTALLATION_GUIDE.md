# MjolnirOS v1.1.0 Installation Guide

## Setup

Install Python 3.12+ and Node.js 20+, create `.venv`, install `requirements.txt`, and run `npm install` followed by `npm install --prefix frontend`. Start the FastAPI Backend with `npm run backend:dev` and the React Frontend with `npm run frontend:dev`, then launch the Electron Desktop Application with `npm run desktop:dev`.

## Desktop Runtime

The desktop runtime supports Windows login startup through Settings and provides Open, Restart, Settings, and Quit tray actions. The Docker frontend is a static Nginx image exposed by Compose at `http://localhost:5173`; the backend remains at port 8000. Production packages should be signed and distributed by the Windows installer pipeline; no updater silently downloads code.
