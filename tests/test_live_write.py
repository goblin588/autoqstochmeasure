"""Regression check: measurement.py must write CSV rows to disk as they're
collected, not just once at the end -- a crash/OS stall during a long run
should lose at most the last unflushed row, not the whole run (see the
2026-11-2x weekend incident this was built for). Runs entirely in
AUTOTOMO_SIM mode."""
import os
import sys
import threading
import time

os.environ.setdefault('AUTOTOMO_SIM', '1')
os.environ.setdefault('DUMP_ENABLED', '0')
sys.path.insert(0, 'src')

import measurement as m


def test_csv_grows_during_collection(tmp_path, monkeypatch):
    monkeypatch.setattr(m.st, 'DATA_DIR', str(tmp_path))

    def fake_acquire_rows(N, total):
        for _ in range(3):
            time.sleep(0.2)
            yield {'herald': 0, 'coinc_ch4': 0, 'int_time': 0.2}

    monkeypatch.setattr(m, '_acquire_rows', fake_acquire_rows)

    def csv_line_count():
        files = list(tmp_path.glob('*_measurement_N3_s0.csv'))
        if not files:
            return 0
        return sum(1 for _ in open(files[0]))

    midrun_counts = []

    def watch():
        for _ in range(15):
            time.sleep(0.1)
            midrun_counts.append(csv_line_count())

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    m.measurement('3', js=[0], duration_s=1.0, auto=True)
    watcher.join(timeout=2)

    final_count = csv_line_count()
    assert final_count == 4  # header + 3 rows

    # at least one snapshot taken WHILE measurement() was still running
    # caught a partial file (more than just the header, fewer than the
    # final total) -- proves rows hit disk incrementally, not in one bulk
    # write after the loop finished
    assert any(1 < n < final_count for n in midrun_counts), midrun_counts


if __name__ == '__main__':
    import tempfile
    from types import SimpleNamespace

    class _Monkeypatch:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path
        test_csv_grows_during_collection(Path(tmp), _Monkeypatch())
    print('test_live_write: ok')
