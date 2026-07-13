# autoqstochmeasure

Automated measurement software for a quantum stochastic process experiment. Interfaces with a TimeTag coincidence counting card and SMC100 motor stages to collect coincidence statistics (with optional output tomography) for the input states of unitaries N=3–6.

## Setup

```bash
uv sync
```

## Entry points

| Script | Purpose |
|--------|---------|
| `python src/measurement.py` | Main menu: set unitary + input state, collect statistics (± tomo), sweep all input states |
| `python src/set_stage_angles.py` | Manually move waveplate stage pairs to a named basis or angle |
| `python src/home_stages.py` | Homes stages which have not been since reset |

`measurement.py` menu options:

1. Set unitary N and the s0 input state
2. Collect statistics (single acquisition, no tomo)
3. Collect statistics with a 6-basis output tomo sweep (H/V/A/D/R/L)
4. Collect statistics for every input state s{j}_N (no tomo)

Results are written to `data/measurement_N{N}_s{label}_{timestamp}.csv`, one row per acquisition with an `input_state` column. Data collected before a crash or Ctrl-C is still saved.

## Project structure

```
src/
├── measurement.py         # Main entry point — measurement menu
├── set_stage_angles.py    # Manually move stage pairs
├── home_stages.py         # Home unreferenced stages
├── hardware/
│   └── detector.py        # Logic16 TimeTag counting card driver (.NET DLL)
├── interfaces/
│   ├── smc100.py          # Newport SMC100 serial driver
│   ├── pm100usb.py        # Thorlabs PM100USB power meter driver
│   ├── tlpmx.py           # Thorlabs TLPMX ctypes binding
│   └── mock.py            # Sim-mode stubs (stages + power meter)
└── libraries/
    ├── settings.py        # Stage IDs, detector channels, delays, sim flag
    ├── basis_vectors.py   # Basis/tomo angles and s{j}_N input-state angles
    ├── waveplate_angles.py# Optimised angle sets for each unitary (U3–U6)
    ├── optics.py          # Jones matrix definitions (HWP, QWP, PBS, mirror)
    ├── tomography.py      # Stage movement helpers
    ├── countingcard.py    # Counting-card acquisition (acquire_counts + streaming tools)
    └── notifier.py        # ntfy.sh push notifications
```

## Sim mode

Run without hardware (mock stages, zero counts):

```bash
AUTOTOMO_SIM=1 python src/measurement.py
# or
python src/measurement.py --sim
```

## Hardware

- **Motor stages:** Newport SMC100 (serial, configured via `COMPORT` in `src/libraries/settings.py`)
- **Coincidence counting:** UQD Logic16 TimeTag card via `hardware/detector.py` (pythonnet + `ttInterface.dll`); herald/signal channels, delays, and coincidence window in `settings.py`
- **Waveplate stages:** input pair (`HWP_IN`/`QWP_IN`), fixed unitary pairs (`IN_2`/`OUT_2`), tomography pairs (`TOM_1`, `TOM_DUMP`)

## Notifications

Push notifications via [ntfy.sh](https://ntfy.sh) are sent on measurement completion. Subscribe to "goblin-lab-r9k2mq" in the ntfy app to receive them.
