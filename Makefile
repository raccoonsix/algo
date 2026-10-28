# Makefile — dev/CI tasks. See AGENTS.md §5 and docs/TEST_PLAN.md §2.
#
# Portable: uses `python -m <tool>` so it works with any activated venv on
# Linux, macOS, or Windows (NFR-007). `make check` MUST pass before any commit.

PYTHON ?= python
PYTEST_MARKS := not network and not llm and not slow

.PHONY: help check test lint typecheck docs-check clean

help:
	@echo "Targets:"
	@echo "  make check      - lint + typecheck + tests (no network/llm/slow) [gate]"
	@echo "  make test       - pytest only (excludes network/llm/slow)"
	@echo "  make lint       - ruff check + ruff format --check"
	@echo "  make typecheck  - mypy --strict on src/"
	@echo "  make docs-check - verify doc cross-reference IDs exist [planned: T-1.6]"
	@echo "  make clean      - remove caches/artifacts"

check: lint typecheck test
	@echo "make check: OK"

test:
	$(PYTHON) -m pytest -m "$(PYTEST_MARKS)"

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy --strict src/

# Placeholder until T-1.6 implements the real cross-reference checker.
docs-check:
	@echo "docs-check: not implemented yet [planned: T-1.6]"

clean:
	$(PYTHON) -c "import shutil,glob,os; [shutil.rmtree(p,ignore_errors=True) for p in glob.glob('**/__pycache__',recursive=True)+['.pytest_cache','.mypy_cache','.ruff_cache','.hypothesis']]"
