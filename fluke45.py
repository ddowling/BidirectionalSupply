import serial
import time

DEFAULT_PORT = '/dev/fluke45'

def find_com_port(hwid_regex):
    import re
    from serial.tools import list_ports

    hwid_regex = re.compile(hwid_regex)

    for port in list_ports.comports():
        if hwid_regex.search(port.hwid):
            return port.device
    return None

def list_com_ports():
    from serial.tools import list_ports
    for port in list_ports.comports():
        if port.hwid and port.hwid != 'n/a':
            print(f'device="{port.device}" description="{port.description}" hwid="{port.hwid}"')

class Fluke45:
    def __init__(self, serial_port, baud=9600, debug=False):
        self.serial = serial.Serial(
            port=serial_port,
            baudrate=baud,
            timeout = 1
        )
        self.debug = debug

        # Send a null command to check if it responds
        self.cmd('')

    def cmd(self, send):
        send_b = send.encode('ascii')
        self.serial.write(send_b + b'\r\n')

        response_b = b''
        while True:
            result = self.serial.readline()
            response_b += result
            if result.endswith(b'>\r\n'):
                break
            time.sleep(0.01)

        if not response_b:
            raise serial.SerialException('Fluke45 Timeout')

        response = response_b.decode('ascii')

        lines = response.split('\r\n')

        want_response = send.endswith('?')
        value = None
        for line in lines:
            if self.debug:
                print(f'line {line}')
            if line == '=>':
                return value
            elif line == '?>':
                raise serial.SerialException('Fluke45 Command Error')
            elif line == '!>':
                raise serial.SerialException('Fluke45 Execution Error')
            else:
                value = line
        raise serial.SerialException('Fluke45 No Prompt')

    def rst(self):
        self.cmd('*RST')

    def idn(self):
        return self.cmd('*IDN?')

    def meas(self):
        str_values = self.cmd('MEAS?')
        values = [ float(str_value) for str_value in str_values.split(',') ]
        return values

    def meas1(self):
        return float(self.cmd('MEAS1?'))

    def meas2(self):
        return float(self.cmd('MEAS2?'))

    def func1(self):
        return self.cmd('FUNC1?')

    def func2(self):
        return self.cmd('FUNC2?')

    def aac(self):
        '''Primary display AC current'''
        self.cmd('AAC')

    def aac2(self):
        '''Secondary display AC current'''
        self.cmd('AAC2')

    def adc(self):
        '''Primary display DC current'''
        self.cmd('ADC')

    def adc2(self):
        '''Secondary display DC current'''
        self.cmd('ADC2')

    def vac(self):
        '''Primary display AC voltage'''
        self.cmd('VAC')

    def vac2(self):
        '''Secondary display AC voltage'''
        self.cmd('VAC2')

    def vdc(self):
        '''Primary display DC voltage'''
        self.cmd('VDC')

    def vdc2(self):
        '''Secondary display DC voltage'''
        self.cmd('VDC2')

    def ohms(self):
        '''Primary display resistance'''
        self.cmd('OHMS')

    def ohms2(self):
        '''Secondary display resistance'''
        self.cmd('OHMS2')

    def diode(self):
        '''Primary display diode'''
        self.cmd('DIODE')

    def diode2(self):
        '''Secondary display diode'''
        self.cmd('DIODE2')

    def freq(self):
        '''Primary display frequency'''
        self.cmd('FREQ')

    def freq2(self):
        '''Secondary display frequency'''
        self.cmd('FREQ2')

    def cont(self):
        '''Primary display continuity'''
        self.cmd('CONT')

    def clr2(self):
        '''Clear secondary display'''
        self.cmd('CLR2')

    def rate(self, r=None):
        '''Get or set the measurement rate (S, M or F)
        S = 2.5 readings per second
        M = 5 readings per second
        F = 20 readings per second
        '''
        if r is None:
            return self.cmd('RATE?')

        self.cmd(f'RATE {r}')

    def auto(self):
        '''Enable auto ranging'''
        self.cmd('AUTO')

    def fixed(self):
        '''Enable fixed range'''
        self.cmd('FIXED')

    def range(self, r=None):
        '''Get or set the range (1-7)'''
        if r is None:
            return self.cmd('RANGE1?')

        self.cmd(f'RANGE {r}')

    # There are some other commands documented in the manual so
    # feel free to add any extras as required
