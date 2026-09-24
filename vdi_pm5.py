"""
(C) 2025 by Patricio.

NOTES:
This driver allows to communicate with a VDI Erickson PM5 Power Meter
using USB comunication.

version 1.0 July 2025
"""

import logging
import serial.tools.list_ports
import serial
import numpy as np

# Configuración básica del logger
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
    )

class PM5Error(Exception):
    pass

class PM5:
    def __init__(self, com_port):
        if not com_port:
            logging.info(f"No COM port was given. Detecting.")
            self.port = self.find_pm5_port()
            logging.info(f"Port: {self.port}")
        else:
            self.port = com_port

        self.connect()

    def connect(self,baudrate=115200):
        try:
            timeout = 1  # segundos

            # Inicializar comunicación
            self.ser_pm5 = serial.Serial(self.port, baudrate, timeout=timeout)
            logging.info(f"Connected to PM5 with port: {self.port}")
        except Exception as e:
            raise PM5Error(f"Failure while connecting PM5: {e}")
        else:
            idn = self.is_connected()
            logging.info(f"Connection established: {idn[1]}")

    def disconnect(self):
        try:
            logging.info("Closing connection with PM5")
            self.ser_pm5.close()
        except Exception as e:
            raise PM5Error(f"Failure while disconnecting PM5 : {e}")

    def _write(self,command):
        try:
            self.ser_pm5.write(command)
        except Exception as e:
            logging.error(f"Failed to send command to PM5: {command} -> {e}")

    def _send_command(self,cmd):
        self.ser_pm5.write(cmd)
        return self._get_command()
    
    def _get_command(self):
        # Leer ACK (0x06)
        ack = self.ser_pm5.read(1)
        if ack != b'\x06':
            logging.error(f"No ACK received, received: {ack}")
        else:
            # Leer la respuesta de 6 bytes
            resp = self.ser_pm5.read(6)
            #print("Respuesta cruda:", resp)
            if len(resp) == 6 and resp[0] == ord('D'):
                # Unpack 16-bit signed integer (little endian)
                countvalue = int.from_bytes(resp[1:3], byteorder='little', signed=True)
                status1 = resp[3]
                status2 = resp[4]
                status3 = resp[5]
                #print(f"Count value: {countvalue}, Status bytes: {status1}, {status2}, {status3}")
                return [countvalue,status1,status2,status3]
            else:
                logging.error(f"Unexpected response: {resp}")

    def _read(self):
        try:
            return self.ser_pm5.readline()
        except Exception as e:
            logging.error(f"Error reading from PM5: {e}")

    def _query(self,command):
        try:
            self.ser_pm5.write(command)
            return self.ser_pm5.readline()
        except Exception as e:
            logging.error(f"Failed to send command to PM5: {command} -> {e}")
    
    def find_pm5_port(self,target_serial='347VA', target_manufacturer='FTDI'):
        puertos = serial.tools.list_ports.comports()
        for p in puertos:
            if (p.serial_number == target_serial) and (p.manufacturer and target_manufacturer in p.manufacturer):
                return p.device
        return None

    def is_connected(self):
        try:
            idn = self._query(b'*IDN?\n')
            return [True, idn]
        except:
            return False

    def get_power(self,unit = 'dBm'):
        reading = self._send_command(b'?D1\x00\x00\x00\x00\r')
        #?D1 : Encabezado del comando. ? indica que es un comando de consulta, D1 indica el canal 1.
        #00\x00\x00\x00 : Datos del comando, en este caso no se envían datos adicionales.
        #\r : Carácter de retorno de carro, indica el final del comando.
        rangemax = 20e-2 #REVISAR SI PUEDO LLAMARLO
        mw_value = reading[0] * 2. * rangemax / 59576.
        #print(f"Potencia medida: {reading} W")
        pow_w = mw_value*1e3    #ajustar para llevar de mW a W.
        pow_pm5_db = np.log10(pow_w)*10
        return pow_pm5_db if unit == 'dBm' else pow_w

    def _get_resolution(self):
        """Returns the resolution of the PM5."""
        reading = self._send_command(b'?R1\x00\x00\x00\x00\r')
        # Assuming the PM5 has a fixed resolution.
        return reading

if __name__ == "__main__":
    """
    Basic test/demo for the PM5.
    """
    #from vdi_pm5 import PM5
    pm5 = PM5.connect()


    try:
        # Perform a measurement
        power_value = PM5.get_power()
        print(f"Measured Power: {power_value.strip()} dBm")
        
    finally:
        PM5.disconnect()
        print("Disconnected.")