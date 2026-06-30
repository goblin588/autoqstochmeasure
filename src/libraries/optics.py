"""
Library for all mathematical definitions of optics 

"""

import numpy as np

ROUND_TO = 8

## Maths ##

def overlap(psi, basis):
    """
    Checks the overlap of psi on the basis state 'basis'
    """
    return np.square(np.abs(np.transpose(np.conjugate(psi))@basis))


## 2X2 Components ##
def HWP(theta):
    theta = np.deg2rad(theta)
    return (-1j)*np.array([[np.round(np.cos(2*theta),ROUND_TO),np.round(np.sin(2*theta),ROUND_TO)],
                           [np.round(np.sin(2*theta),ROUND_TO),np.round(-1*np.cos(2*theta),ROUND_TO)]])

def QWP(theta):
    theta = np.deg2rad(theta)
    return (1/np.sqrt(2))*np.array([[np.round(1-(1j*np.cos(2*theta)),ROUND_TO),np.round(-1j*np.sin(2*theta),ROUND_TO)],
                                    [np.round(-1j*np.sin(2*theta),ROUND_TO),np.round(1+1j*np.cos(2*theta),ROUND_TO)]])

## 4X4 Components##

def Mirror4(phi, phi2):
    # ASSUMING PHI RELATIVE PHASE SHIFT IN RADIANS
    m = np.array([[1,0,0,0],
        [0,np.exp(1j*phi),0,0],
        [0,0,1,0],
        [0,0,0,np.exp(1j*phi2)]])
    return m 

def HWP_p1(theta):
    theta = np.deg2rad(theta)
    return (-1j)*np.array([[np.round(np.cos(2*theta),ROUND_TO),np.round(np.sin(2*theta),ROUND_TO),0,0],[np.round(np.sin(2*theta),ROUND_TO),np.round(-1*np.cos(2*theta),ROUND_TO),0,0],
                           [0,0,1j,0],[0,0,0,1j]])

def HWP_p2(theta):
    theta = np.deg2rad(theta)
    return (-1j)*np.array([[1j,0,0,0],[0,1j,0,0],
                            [0,0,np.round(np.cos(2*theta),ROUND_TO),np.round(np.sin(2*theta),ROUND_TO)],[0,0,np.round(np.sin(2*theta),ROUND_TO),np.round(-1*np.cos(2*theta),ROUND_TO)]])

def QWP_p1(theta):
    theta = np.deg2rad(theta)
    return (1/np.sqrt(2))*np.array([[np.round(1-(1j*np.cos(2*theta)),ROUND_TO),np.round(-1j*np.sin(2*theta),ROUND_TO),0,0],[np.round(-1j*np.sin(2*theta),ROUND_TO),np.round(1+1j*np.cos(2*theta),ROUND_TO),0,0],
                                    [0,0,np.sqrt(2),0],[0,0,0,np.sqrt(2)]])

def QWP_p2(theta):    
    theta = np.deg2rad(theta)
    return (1/np.sqrt(2))*np.array([[np.sqrt(2),0,0,0],[0,np.sqrt(2),0,0],
                                      [0,0,np.round(1-(1j*np.cos(2*theta)),ROUND_TO),np.round(-1j*np.sin(2*theta),ROUND_TO)],[0,0,np.round(-1j*np.sin(2*theta),ROUND_TO),np.round(1+(1j*np.cos(2*theta)),ROUND_TO)]])

PBS = np.array([[1,0,0,0],
            [0,0,0,1j],
            [0,0,1,0],
            [0,1j,0,0]])

PBS_dag = np.conjugate(np.transpose(PBS))
    
