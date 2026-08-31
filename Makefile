.PHONY: install dev backend frontend test typecheck

install:
	cd backend && uv sync
	cd frontend && pnpm install

dev:
	$(MAKE) -j2 backend frontend

backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && pnpm dev

test:
	cd backend && uv run pytest

typecheck:
	cd backend && uv run pyright
	cd frontend && pnpm exec tsc --noEmit
