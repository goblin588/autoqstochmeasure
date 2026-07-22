"""
Plotting, normalisation, and unitary math for setup characterisations.

Ported from autotomo's libraries/plotting.py — optics.py, basis_vectors.py,
and waveplate_angles.py are identical between the two repos, so the unitary
math needs no changes. Only the bar-label unit changed (raw_val is a photon
count here, not a power-meter reading in mV).
"""

import csv
import datetime
import math
import os

import matplotlib.pyplot as plt
import numpy as np

import libraries.optics as ol
from libraries.optics import PBS, PBS_dag
from libraries.basis_vectors import (basis_vectors, basis_vectors_p1,
                                     basis_vectors_2, process_state_angles)

ROUND_TO = 8  # decimal places used in matrix rounding


# ── Normalisation ─────────────────────────────────────────────────────────────

def normalise_pair(val1: float, val2: float) -> tuple[float, float]:
    total = val1 + val2
    if total == 0:
        return 0.5, 0.5
    return val1 / total, val2 / total


def normalise_err(meas1, meas2, norm1: float, norm2: float) -> tuple[float, float]:
    # meas[0] can be a genuine 0 photon count (unlike a power-meter mW
    # reading, which is never exactly 0.0) — guard the division for that.
    err1 = (meas1[1] / meas1[0]) * norm1 if meas1[0] else 0.0
    err2 = (meas2[1] / meas2[0]) * norm2 if meas2[0] else 0.0
    return err1, err2


def normalise_measurements(measurements: dict) -> dict:
    normalized = {}
    for k1, k2 in [("H", "V"), ("A", "D"), ("R", "L")]:
        normalized[k1] = [0, 0]
        normalized[k2] = [0, 0]
        normalized[k1][0], normalized[k2][0] = normalise_pair(measurements[k1][0], measurements[k2][0])
        normalized[k1][1], normalized[k2][1] = normalise_err(
            measurements[k1], measurements[k2], normalized[k1][0], normalized[k2][0]
        )
    return normalized


def normalise_full_tomo_data(res: dict) -> dict:
    """
    Normalise nested tomo result.
    Input:  {input_state: {output_state: (count, err)}}
    Output: {input_state: {output_state: [norm_val, norm_err]}}
    """
    normalized = {}
    for input_state in res:
        normalized[input_state] = {}
        for k1, k2 in [("H", "V"), ("A", "D"), ("R", "L")]:
            normalized[input_state][k1] = [0, 0]
            normalized[input_state][k2] = [0, 0]
            normalized[input_state][k1][0], normalized[input_state][k2][0] = normalise_pair(
                res[input_state][k1][0], res[input_state][k2][0]
            )
            normalized[input_state][k1][1], normalized[input_state][k2][1] = normalise_err(
                res[input_state][k1], res[input_state][k2],
                normalized[input_state][k1][0], normalized[input_state][k2][0],
            )
    return normalized


# ── Unitary math ──────────────────────────────────────────────────────────────

def getUnitary(qf2=0, hf2=0, qf1=0, hf1=0, m3=0, m2=0, h2=0, q2=0,
               m1=0, h1=0, q1=0, qin2=0, hin2=0, path=2) -> np.ndarray:
    """Return 4×4 unitary matrix for the current waveplate angle configuration.

    The analyzer pair on the measured `path` (f1/TOM_1 for path 1, f2/OUT_2 for
    path 2) is excluded from U — it is modeled by the basis projection in
    UnitaryToProb. The opposite path's pair stays in U at its fixed angles.
    """
    HWP2   = ol.HWP_p2(h2);   QWP2   = ol.QWP_p2(q2)
    HWP1   = ol.HWP_p1(h1);   QWP1   = ol.QWP_p1(q1)
    QWPin2 = ol.QWP_p2(qin2); HWPin2 = ol.HWP_p2(hin2)
    M3 = ol.Mirror4(m3, m1)
    M2 = ol.Mirror4(m2, m2)
    M1 = ol.Mirror4(m1, m3)
    U = PBS_dag @ M3 @ M2 @ M1 @ HWP2 @ QWP2 @ HWP1 @ QWP1 @ PBS @ HWPin2 @ QWPin2
    if path == 2:
        return ol.HWP_p1(hf1) @ ol.QWP_p1(qf1) @ U
    return ol.HWP_p2(hf2) @ ol.QWP_p2(qf2) @ U


def input_state_vector(basis: str) -> np.ndarray:
    """4-vector for a named input basis, or an s{j}_{N} process state computed
    from its prep angles: QWP(q) @ HWP(h) @ |H> (input arm is HWP-then-QWP),
    embedded in path 2 like the named basis vectors.
    """
    if basis in basis_vectors:
        return basis_vectors[basis]
    hwp, qwp = process_state_angles[basis]
    v = np.asarray(ol.QWP(qwp) @ ol.HWP(hwp) @ basis_vectors_2['H'])
    return np.vstack([np.zeros((2, 1)), v])


def UnitaryToProb(U: np.ndarray, input: np.ndarray, path: int = 2) -> dict:
    """Convert unitary to probability distribution over measurement basis pairs.

    path: which output path to project onto (1 or 2, default 2).
    """
    epsilon = 1e-12
    mb = basis_vectors if path == 2 else basis_vectors_p1
    res = {}
    output = U @ input

    def inner_prod_sq(bra, ket):
        val = np.conjugate(np.transpose(bra)) @ ket
        return float(np.squeeze(np.asarray(np.square(np.abs(val)))))

    for k1, k2 in [("H", "V"), ("A", "D"), ("R", "L")]:
        p1 = inner_prod_sq(mb[k1], output)
        p2 = inner_prod_sq(mb[k2], output)
        denom = p1 + p2 + epsilon
        res[k1] = p1 / denom
        res[k2] = p2 / denom

    return res


# ── Private plot helpers ──────────────────────────────────────────────────────

def _unitary_from_angles(angles: dict, path: int = 2) -> np.ndarray:
    return getUnitary(
        q1=angles['q1'],           h1=angles['h1'],
        q2=angles['q2'],           h2=angles['h2'],
        qf2=angles['qf2'],         hf2=angles['hf2'],
        qf1=angles.get('qf1', 0),  hf1=angles.get('hf1', 0),
        qin2=angles['qin2'],       hin2=angles['hin2'],
        m1=angles['m1'],           m2=angles['m2'],  m3=angles['m3'],
        path=path,
    )


def _make_directory_name(plot_type: str | None = None, note: str | None = None) -> str:
    if plot_type is not None:
        name = datetime.datetime.now().strftime(
            f"Figures/Figures_%Y-%m-%d/{plot_type}_Figures_%Y-%m-%d/%Y-%m-%d__%H-%M"
        )
    else:
        name = datetime.datetime.now().strftime("Figures/Figures_%Y-%m-%d/%Y-%m-%d__%H-%M")
    if note is not None:
        name = f'{note}_{name}'
    return name


def _subplot_grid(n: int):
    """Return (fig, axes_list) for n subplots in a 2-column layout."""
    if n == 1:
        fig, ax = plt.subplots(1, 1, figsize=(14, 8))
        return fig, [ax]
    cols = 2
    rows = math.ceil(n / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(28, 10 * rows))
    axes_flat = axes.ravel().tolist()
    for spare in axes_flat[n:]:
        spare.set_visible(False)
    return fig, axes_flat[:n]


def _render_basis_subplot(ax, basis: str, norm_slice: dict, theory: dict,
                          raw_slice: dict | None = None) -> float:
    """
    Draw measured vs theoretical bars for one input basis onto ax.
    norm_slice: normalized_data[basis]  — {state: [value, err]}
    theory:     {state: float}
    raw_slice:  data[basis]             — {state: (raw_count, raw_err)}, for count labels
    Returns L2 fit residual.
    """
    labels = list(basis_vectors.keys())
    measured = [norm_slice[k][0] for k in labels]
    err      = [norm_slice[k][1] for k in labels]
    theory_vals = [theory[k] for k in labels]
    x = np.arange(len(labels))
    bar_width = 0.35

    bars = ax.bar(x, measured, width=bar_width, color='gold', label='Measured')

    if raw_slice is not None:
        for j, bar in enumerate(bars):
            raw_val, raw_err = raw_slice[labels[j]]
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.05,
                f"{raw_val:.0f} ± {raw_err:.0f} counts",
                ha='center', va='bottom', fontsize=15,
            )

    ax.bar(x, theory_vals, width=bar_width, color='none', edgecolor='black',
           linestyle=':', linewidth=2, label='Theoretical')
    ax.errorbar(labels, measured, yerr=err, fmt='s', color='k')
    ax.set_title(f'|{basis}⟩ Input', fontsize=30)
    ax.set_xlabel('State', fontsize=30)
    ax.set_ylabel('Probability', fontsize=30)
    ax.set_ylim(0, 1)
    ax.set_xticks(x + bar_width / 2)
    ax.set_xticklabels(labels, fontsize=30)
    ax.tick_params(axis='y')
    ax.legend(fontsize=20)

    return float(np.linalg.norm(np.array(measured) - np.array(theory_vals)))


def _save_outputs(fig, data: dict, normalized_data: dict, angles: dict, graph_title: str,
                  directory_name: str, plot_type: str | None,
                  save_plot: bool, save_data: bool) -> None:
    if save_plot:
        try:
            savePlot(fig, graph_title='', filepath=directory_name)
        except Exception as e:
            print(f"Error saving plot: {e}\n  Retrying...")
            try:
                savePlot(fig, graph_title=graph_title, filepath=directory_name)
            except Exception as e2:
                print(f"Failed saving plot: {e2}")
        print(f"Plot saved to: {directory_name}")

    if save_data:
        try:
            saveData(graph_title='', data=data, normalised_data=normalized_data,
                     angles=angles, filepath=directory_name, plot_type=plot_type)
        except Exception as e:
            print(f"Error saving data: {e}\n  Retrying...")
            try:
                saveData(graph_title=graph_title, data=data, normalised_data=normalized_data,
                         angles=angles, filepath=directory_name, plot_type=plot_type)
            except Exception as e2:
                print(f"Failed saving data: {e2}")
        print(f"Data saved to: {directory_name}")


# ── Public plotting API ───────────────────────────────────────────────────────

def plot_characterisation(data: dict, graph_title: str, angles: dict,
                          plot_type: str | None = None, note: str | None = None,
                          save_plot: bool = True, save_data: bool = True,
                          show_plot: bool = True, path: int = 2) -> None:
    """
    Plot measured vs theoretical probabilities for all input bases in data.
    Works for any number of bases — subplots scale in a 2-column layout.
    data: {input_basis: {output_state: (raw_count, raw_err)}}
    """
    U = _unitary_from_angles(angles, path=path)
    normalized_data = normalise_full_tomo_data(data)
    bases = list(normalized_data.keys())

    fig, axes = _subplot_grid(len(bases))

    fit = 0.0
    for ax, basis in zip(axes, bases):
        theory = UnitaryToProb(U, input_state_vector(basis), path=path)
        fit += _render_basis_subplot(ax, basis, normalized_data[basis], theory,
                                     raw_slice=data[basis])

    plt.subplots_adjust(left=0.05, right=0.95, top=0.9, bottom=0.05, wspace=0.25, hspace=0.3)

    directory_name = _make_directory_name(plot_type, note)
    _save_outputs(fig, data, normalized_data, angles, graph_title, directory_name,
                  plot_type, save_plot, save_data)

    print(f"Measured value solution fit: {fit:.4f}")
    if show_plot:
        plt.show()
    return fit


def plot_mirror(normalized_data: dict, categories: list) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    axes = axes.ravel()
    for i, (key, measurements) in enumerate(normalized_data.items()):
        normalized_values = [measurements[cat] for cat in categories]
        axes[i].bar(np.arange(len(categories)), normalized_values, color='gold', label=key)
        axes[i].set_ylim(0, 1)
        axes[i].set_title(f'{key} Normalized Measurements')
        axes[i].set_xlabel('State')
        axes[i].set_ylabel('Normalized Power')
        axes[i].set_xticks(np.arange(len(categories)))
        axes[i].set_xticklabels(categories)
        axes[i].legend()
    plt.tight_layout()
    plt.show()


# ── File I/O ──────────────────────────────────────────────────────────────────

def createDir(directory_name: str) -> int:
    try:
        os.makedirs(directory_name, exist_ok=True)
        print(f"Directory '{directory_name}' created successfully.")
    except PermissionError:
        print(f"Permission denied: Unable to create '{directory_name}'.")
    except Exception as e:
        print(f"An error occurred: {e}")
    return 1


def savePlot(fig, graph_title: str, filepath: str = os.getcwd()) -> None:
    if createDir(filepath):
        fig.savefig(filepath + '/' + graph_title + '_FIGURE.png')


def saveData(data: dict, normalised_data: dict, angles: dict, graph_title: str,
             plot_type: str | None = None, filepath: str = os.getcwd()) -> None:
    if createDir(filepath):
        writeData2File(filepath + '/' + graph_title + '_DATA',
                       data=data, normalised_data=normalised_data,
                       angles=angles, plot_type=plot_type)


def writeData2File(filename: str, data: dict, normalised_data: dict,
                   angles: dict, plot_type: str | None) -> None:
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(f"{filename}.csv", 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, delimiter=' ', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        if plot_type is not None:
            writer.writerow([f'PLOT TYPE: {plot_type}'])
        writer.writerow([f'DATE: {datetime.datetime.now().strftime("%Y/%m/%d @ %H:%M:%S")}'])
        writer.writerow([f'ANGLES: {angles}'])

        if '0' in data.keys() or 0 in data.keys():
            for key in data:
                writer.writerow([f'RAW DATA [{key}]: {data[key]}'])
        else:
            writer.writerow([f'RAW_DATA: {data}'])

        if '0' in normalised_data.keys() or 0 in normalised_data.keys():
            for key in normalised_data:
                writer.writerow([f'NORM_DATA[{key}]: {normalised_data[key]}'])
        else:
            writer.writerow([f'NORM_DATA: {normalised_data}'])
