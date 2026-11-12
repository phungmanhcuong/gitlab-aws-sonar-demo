# Local shortcuts. The pipeline runs the same commands (ci/*.yml).
.PHONY: setup check test run image tf-check

setup:          ## install dependencies into app/.venv
	cd app && uv sync --locked

check: test     ## everything the merge request pipeline runs on code
	cd app && uv run ruff check . && uv run ruff format --check . && uv run mypy

test:
	cd app && uv run pytest

run:            ## the API on http://127.0.0.1:8080 with an in-memory store
	cd app && uv run uvicorn shortlinks.main:app --port 8080 --reload

image:          ## the Lambda image, runnable locally: docker run -p 8080:8080 shortlinks:local
	docker build --provenance=false -t shortlinks:local app

tf-check:
	terraform fmt -check -recursive infra
	for s in shared service; do terraform -chdir=infra/stacks/$$s init -backend=false >/dev/null && terraform -chdir=infra/stacks/$$s validate; done
