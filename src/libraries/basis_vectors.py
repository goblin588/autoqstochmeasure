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

# For projection in tomography
# Angles [HWP, QWP] 
basis_angles = {
    "H": [0,0],
    "V": [45,0],
    "A": [-22.5,45],
    "D": [22.5,45],
    "R": [22.5,0],
    "L": [-22.5,0],
    "s0_3": [302.88, 147.052],
    "s0_4": [290.14, 118.88], 
    "s0_5": [104.33, 131.71], 
    "s0_6": [39.35, 50.344]
}

# import OpticsLib as ol

# input_state = basis_vectors_2["V"]

# # print(ol.HWP(basis_angles["D"][0]))
# # print(ol.QWP(basis_angles["D"][1]))
# # print(np.transpose(input_state))

# out = ol.QWP(0)@ol.HWP(-22.5)@input_state

# overlap = np.abs(np.conjugate(np.transpose(out))@basis_vectors_2["L"])**2
# print(overlap)