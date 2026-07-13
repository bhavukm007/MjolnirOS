# MjolnirOS v1.0 Installation Guide

Install Python 3.12+ and Node.js 20+, create `.venv`, install `requirements.txt`, and run `npm install`. Start development services with `npm run backend:dev` and `npm run frontend:dev`, then launch Electron with `npm run desktop:dev`.

The desktop runtime supports Windows login startup through Settings and provides a tray menu. Production packages should be signed and distributed by the Windows installer pipeline; no updater silently downloads code.
