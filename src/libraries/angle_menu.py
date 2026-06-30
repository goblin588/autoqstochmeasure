import numpy as np
from libraries.waveplate_angles import unitaries_angles

def angle_menu(): 
    # ADD HF1 and QF1, and include N number 3-6
    angles = {'q1': 0,
              'h1': 0,
              'q2': 0,
              'h2': 0,
              'qf1': 0,
              'hf1': 0,
              'qf2': 0,
              'hf2': 0,
              'qin2': 0,
              'hin2': 0,
              'm3': 3.74,
              'm2': 3.77,
              'm1': 3.16,
              'title': ''}  
    u = input("What N unitary are you using?")
    if u in unitaries_angles.keys():
        U = unitaries_angles[u]
    else:
        U = unitaries_angles['3']
        u = '3'
    angles['N'] = u
    print("What angles should be set for internal waveplates?")
    print("Enter: \n\t1.  U for all U angles")
    print("\t 2. Any of the following: 'q1', 'h1', 'q2', 'h2', 'qf1', 'hf1', 'qf2', 'hf2', 'qin2', 'hin2'")
    print("\t 3. Type 'set' to set a component to a specific angle")
    print("\t 4. Type 'c' to check the current angles")
    print("\t 5. Type 'set' to set a specific angle for a component")
    print("or, press enter to set remaining angles to 0 and continue")

    # Set Angles Loop 
    next = False
    while not next:
        user_input = input()
        if user_input == '':
            print("Setting remaining angles to 0")
            next = True
        elif user_input.upper() == 'U':
            print("Setting all angles to U angles")
            angles = U.copy()
            angles['title'] = 'U'
            angles['N'] = u
            next = True
        elif user_input in angles.keys() and user_input not in ('N', 'title'):
                print("Setting {} to {}".format(user_input, U[user_input]))
                angles[user_input] = U[user_input]
                angles['title'] += '{}({}), '.format(user_input, U[user_input])
                print("Set next angle or press enter to continue: ", end="")
        elif user_input.lower() =='c':
                print("Current Angles: {}".format(angles))
                print("Set next angle or press enter to continue: ", end="")
        elif user_input.lower() == 'set':
            component = input("Enter the component name ('q1', 'h1', 'q2', 'h2', 'qf1', 'hf1', 'qf2', 'hf2', 'qin2', 'hin2'): ")
            if component in angles.keys():
                angle_value = float(input(f"Enter the angle for {component}: "))
                angles[component] = angle_value
                print(f"Set {component} to {angle_value}")
                angles['title'] += '{}({}), '.format(component, angle_value)
                print("Set next angle or press enter to continue: ", end="")
            else:
                print("Invalid component name. Please try again.")
        else:
            print("Invalid input. Please enter one of the following: 'q1', 'h1', 'q2', 'h2', 'qf1', 'hf1', 'qf2', 'hf2', 'qin2', 'hin2' or 'U' for all U angles.")
            print("Or press enter to set remaining angles to 0 and continue")
    
    if angles['title'] != 'U':
        angles['title'] = generate_title(angles)
    print("Chosen angles: ", angles)
    return angles

def generate_title(angles):
    components_list = ['q1', 'h1', 'q2', 'h2', 'qf1', 'hf1', 'qf2', 'hf2', 'qin2', 'hin2']
    title = ''
    for key in angles.keys():
        if key in components_list and angles[key] != 0:
            title += f'{key}[{angles[key]}]_'
    title = title.rstrip('_')
    if title == '':
        title = 'Zeroes'
    return title