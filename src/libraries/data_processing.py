"""
filename: Data-Processor.py

"""
import ast
import re
from collections import defaultdict
import numpy as np

def clean_np_float(text: str) -> str:
    return re.sub(r'np\.float64\(([^)]+)\)', r'\1', text)

def load_csv_data(path):
    data = {
        "plot_type": None,
        "date": None,
        "angles": None,
        "raw_data": {},
        "norm_data": {}
    }

    with open(path, "r") as f:
        for line in f:
            line = line.strip().strip('"')  # remove quotes & whitespace

            if line.startswith("PLOT TYPE:"):
                data["plot_type"] = line.split(":", 1)[1].strip()

            elif line.startswith("DATE:"):
                data["date"] = line.split(":", 1)[1].strip()

            elif line.startswith("ANGLES:"):
                raw_angles = line.split(":", 1)[1].strip()
                data["angles"] = ast.literal_eval(clean_np_float(raw_angles))

            elif line.startswith("RAW_DATA"):
                _, content = line.split(":", 1)

                # Check for [index]
                if line.startswith("RAW_DATA["):
                    key = int(line.split("[")[1].split("]")[0])
                else:
                    key = 0  # single dataset

                safe_content = clean_np_float(content)
                data["raw_data"][key] = ast.literal_eval(safe_content)

            elif line.startswith("NORM_DATA"):
                _, content = line.split(":", 1)

                if line.startswith("NORM_DATA["):
                    key = int(line.split("[")[1].split("]")[0])
                else:
                    key = 0

                safe_content = clean_np_float(content)
                data["norm_data"][key] = ast.literal_eval(safe_content)

    return data


def average_measurements(raw_data, return_std=True):
    # Collating all results into lists 
    res_arrays = defaultdict(lambda: defaultdict(list))
    res_out = defaultdict(lambda: defaultdict(list))

    for run in raw_data:
        for input in raw_data[run].keys():
            for output in raw_data[run][input].keys():
                res_arrays[input][output].append(raw_data[run][input][output][0])

    # Averaging + Std on each measurement Set 
    for input in res_arrays.keys():
        for output in  ['H', 'V', 'A', 'D', 'R', 'L']:
            res_out[input][output] = [0, 0]
            res_out[input][output][0] = np.average(res_arrays[input][output])
            res_out[input][output][1] = np.std(res_arrays[input][output])

    return res_out
