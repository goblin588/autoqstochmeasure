"""Regression check for the mid-measurement pause key: typing 'p' must
block collection in place (no rows discarded, no crash) until 'p' is typed
again. Runs entirely in AUTOTOMO_SIM mode."""
import os
import sys
import time

os.environ.setdefault('AUTOTOMO_SIM', '1')
os.environ.setdefault('DUMP_ENABLED', '0')
sys.path.insert(0, 'src')

import measurement as m


def test_pause_then_resume_keeps_all_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(m.st, 'DATA_DIR', str(tmp_path))
    monkeypatch.setattr(m.time, 'sleep', lambda s: None)

    def fake_acquire_rows(N, total):
        for _ in range(3):
            yield {'herald': 0, 'coinc_ch4': 0, 'int_time': 0.2}

    monkeypatch.setattr(m, '_acquire_rows', fake_acquire_rows)

    # row1: 'p' pauses; one still-waiting poll (None); 'p' resumes.
    # row2, row3: no key pressed -> no pause.
    keys = iter(['p', None, 'p', None, None])
    monkeypatch.setattr(m, '_key_pressed', lambda: next(keys, None))

    m.measurement('3', js=[0], duration_s=1.0, auto=True)

    [csv_file] = tmp_path.glob('*_measurement_N3_s0.csv')
    with open(csv_file) as f:
        assert sum(1 for _ in f) == 4  # header + 3 rows, nothing lost to the pause


if __name__ == '__main__':
    import tempfile
    from pathlib import Path

    class _MP:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    with tempfile.TemporaryDirectory() as tmp:
        test_pause_then_resume_keeps_all_rows(Path(tmp), _MP())
    print('test_pause: ok')
