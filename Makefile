.PHONY: all test sample demo inspect help verify

# Zero-Dependency Hackathon Makefile
PYTHON ?= python

all: test

help:
	@echo "SQRay - Zero-Dependency SQLite Deep-Inspection & B-Tree Visualizer"
	@echo ""
	@echo "Available commands:"
	@echo "  make test      Run zero-dependency standard library test suite"
	@echo "  make sample    Generate synthetic test SQLite & WAL databases"
	@echo "  make inspect   Inspect database header & schema (demo.db)"
	@echo "  make tree      Visualize multi-level B-Tree hierarchy (btree.db)"
	@echo "  make wal       Audit Write-Ahead Log frames (wal.db)"
	@echo "  make map       Render 2D page allocation grid (btree.db)"
	@echo "  make dump      Extract binary table rows without drivers (demo.db)"
	@echo "  make verify    Generate dependency proof (deps-proof.txt)"

test:
	$(PYTHON) -m unittest test_sqray.py -v

sample:
	$(PYTHON) generate_samples.py

inspect:
	$(PYTHON) sqray.py inspect demo.db

tree:
	$(PYTHON) sqray.py tree btree.db

wal:
	$(PYTHON) sqray.py wal wal.db

map:
	$(PYTHON) sqray.py map btree.db

dump:
	$(PYTHON) sqray.py dump demo.db items

verify:
	$(PYTHON) -c "import sqray; import sys; print('Imported modules:'); print('\n'.join(sorted(set(m.split('.')[0] for m in sys.modules if not m.startswith('_')))))"
