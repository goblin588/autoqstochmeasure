from ctypes import c_uint32,byref,create_string_buffer,c_bool,c_char_p,c_int,c_double
from interfaces.tlpmx import TLPMX
import time
import numpy as np 
from interfaces.tlpmx import TLPM_DEFAULT_CHANNEL

class PM100USB:
    def __init__(self, wavelength=780, verbose=False):
        """
        Initialize the PM100USB power meter.
        """
        self.tlPM = TLPMX()
        self.device_count = c_uint32()
        try:
            self.tlPM.findRsrc(byref(self.device_count))
        except Exception as e:
            print(f"Error finding POWER METER: {e} \n Terminating program...")
            exit()
    
        self.resource_name = create_string_buffer(1024)
        
        for i in range(0, self.device_count.value):
            self.tlPM.getRsrcName(c_int(i), self.resource_name)
            if verbose:
                # Print the resource name of each device.
                print("Resource name of device", i, ":", c_char_p(self.resource_name.raw).value, "\n")
        
        # Connect to the specified device.
        self.tlPM.open(self.resource_name, c_bool(True), c_bool(True))
        
        # self.wavelength = c_double(wavelength)  # Set wavelength.
        # self.tlPM.setWavelength(self.wavelength, TLPM_DEFAULT_CHANNEL)
        
        # self.tlPM.setPowerAutoRange(c_int16(1), TLPM_DEFAULT_CHANNEL)  # Set auto range to 1 (on).
        # self.tlPM.setPowerUnit(c_int16(0), TLPM_DEFAULT_CHANNEL)       # Set power unit to W (0).

    def __enter__(self):
        """
        Enter the context manager.
        """
        return self
    def __exit__(self, exc_type, exc_value, traceback):
        """
        Exit the context manager.
        """
        time.sleep(0.1)  # Wait for a second before closing.
        self.close()
    
    def read(self, n = 30):
        """
        Returns avg of n power measurements. and std
        """
        data = []
        for i in range(n):
            sample = c_double()
            self.tlPM.measPower(byref(sample), TLPM_DEFAULT_CHANNEL)
            data.append(sample.value)   
             
        return sum(data)/n, np.std(data, ddof=1)

    def close(self):
        """
        Close the connection to the power meter.
        """
        self.tlPM.close()

# with PM100USB(wavelength=780, verbose=True) as pm:
#     print('Power' , pm.get_power())