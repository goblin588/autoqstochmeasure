#%%

import numpy as np

# 4x1 Vectors — setup ordering: (H_p1, V_p1, H_p2, V_p2)

H = np.transpose(np.matrix([0,0,1,0]))
V = np.transpose(np.matrix([0, 0, 0, 1]))
A = (1/np.sqrt(2))*(H-V)
D = (1/np.sqrt(2))*(H+V)
R = (1/np.sqrt(2))*(H-(1j*V))
L = (1/np.sqrt(2))*(H+(1j*V))

basis_vectors = {
    "H": H,
    "V": V,
    "A": A,
    "D": D,
    "R": R,
    "L": L
}

H_p1 = np.transpose(np.matrix([1,0,0,0]))
V_p1 = np.transpose(np.matrix([0,1,0,0]))
A_p1 = (1/np.sqrt(2))*(H_p1-V_p1)
D_p1 = (1/np.sqrt(2))*(H_p1+V_p1)
R_p1 = (1/np.sqrt(2))*(H_p1-(1j*V_p1))
L_p1 = (1/np.sqrt(2))*(H_p1+(1j*V_p1))

basis_vectors_p1 = {
    "H": H_p1,
    "V": V_p1,
    "A": A_p1,
    "D": D_p1,
    "R": R_p1,
    "L": L_p1
}

# 2x1 Vectors 

H_2 = np.transpose(np.matrix([1,0]))
V_2 = np.transpose(np.matrix([0,1]))
A_2 = (1/np.sqrt(2))*(H_2-V_2)
D_2 = (1/np.sqrt(2))*(H_2+V_2)
R_2 = (1/np.sqrt(2))*(H_2-(1j*V_2))
L_2 = (1/np.sqrt(2))*(H_2+(1j*V_2)) 

basis_vectors_2 = {
    "H": H_2,
    "V": V_2,
    "A": A_2,
    "D": D_2,
    "R": R_2,
    "L": L_2
}

# State-prep angles [HWP, QWP]: input arm is HWP-then-QWP, so these take H -> basis.
basis_angles = {
    "H": [0,0],
    "V": [45,0],
    "A": [-22.5,45],
    "D": [22.5,45],
    "R": [-22.5,0],
    "L": [22.5,0],
}

# Analyzer angles [HWP, QWP]: tomography arm is QWP-then-HWP, so these take basis -> H.
# Same HWP angle as basis_angles, QWP angle shifted by 90 (QWP(t)^-1 == QWP(t+90)).
tomo_angles = {
    name: [hwp, qwp + 90 if qwp <= 0 else qwp - 90]
    for name, (hwp, qwp) in basis_angles.items()
}

process_state_angles = {
    # N = 3
    "s0_3": [302.884, 147.052],
    "s1_3": [100.525,  30.651],
    "s2_3": [ 93.382,  12.532],
    "s3_3": [264.736,  81.200],
    # N = 4
    "s0_4": [290.143, 118.880],
    "s1_4": [104.620,  49.132],
    "s2_4": [292.974,  66.474],
    "s3_4": [303.283,  82.611],
    "s4_4": [ 46.569,  98.613],
    # N = 5
    "s0_5": [104.327, 131.714],
    "s1_5": [106.012, 122.681],
    "s2_5": [197.463, 116.362],
    "s3_5": [198.004, 109.262],
    "s4_5": [171.008,   6.790],
    "s5_5": [355.705,  19.311],
    # N = 6
    "s0_6": [ 39.349,  50.344],
    "s1_6": [ 31.059,  46.660],
    "s2_6": [199.611, 135.121],
    "s3_6": [ 23.196, 133.962],
    "s4_6": [105.889,  42.714],
    "s5_6": [279.790,  40.708],
    "s6_6": [214.120, 123.429],
}

if __name__ == "__main__":
    # Scratch check: prep D then analyze with HWP(22.5)/QWP(0), print overlaps.
    import optics as ol

    basis = "D"

    input_state = basis_vectors_2["H"]

    out = ol.QWP(0)@ol.HWP(22.5)@ol.QWP(-basis_angles[basis][1])@ol.HWP(-basis_angles[basis][0])@input_state

    for basis in basis_angles.keys():
        overlap = np.abs(np.conjugate(np.transpose(out)) @ basis_vectors_2[basis])**2
        print(f'{basis}: {overlap}')