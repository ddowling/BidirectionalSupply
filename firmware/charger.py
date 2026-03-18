# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
#
# Battery charger state machine for the BQ25758 bidirectional DC/DC converter.
#
# Implements a 3-stage CC/CV profile with pre-charge:
#   Waiting     : Polling until Vin >= v_min_input and Vbat >= v_cutoff
#   Pre-charge  : Vbat < v_precharge  → charge at i_precharge (low current)
#   Fast charge : Vbat >= v_precharge → charge at i_fast (CC mode)
#   Taper       : Vbat >= v_reg       → converter holds voltage (CV mode),
#                                        current tapers naturally
#   Done        : Iout < i_term for N consecutive readings → disable output
#   Fault       : Safety timeout exceeded. Auto-retries via Waiting after delay.
#
# The charger drives the BQ25758 via BoardContext.set() calls and reads
# voltage/current/mode via BoardContext.get().  It has no direct hardware
# dependency and can be tested offline.
#
# Usage:
#   import charger, board
#   board.set_charger(charger.BatteryCharger(charger.LIFEPO4_2S_5AH))
#
from micropython import const
import time

# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------
STATE_IDLE      = const(0)
STATE_PRECHARGE = const(1)
STATE_FAST      = const(2)
STATE_TAPER     = const(3)
STATE_DONE      = const(4)
STATE_FAULT     = const(5)
STATE_WAITING   = const(6)
STATE_DISCHARGE = const(7)

_STATE_NAMES = ('Idle', 'Pre', 'Fast', 'Taper', 'Done', 'Fault', 'Wait', 'Disch')

# Seconds in FAULT before auto-retrying via WAITING
_FAULT_RETRY_S = const(30)

# Consecutive readings below i_term required to declare DONE
_ITERM_CONSEC = const(5)


# ---------------------------------------------------------------------------
# Charging profile
# ---------------------------------------------------------------------------
class ChargingProfile:
    '''Parameters for a single battery chemistry / pack configuration.

    Args:
        name          : Human-readable label shown on display and in logs.
        v_min_input   : Minimum input voltage to begin/continue charging (V).
                        Charger waits in WAITING state until Vin >= this.
        v_cutoff      : Minimum safe battery voltage (V). Charger waits in
                        WAITING state until Vbat >= this.
        v_precharge   : Pre-charge to fast-charge transition voltage (V).
        v_reg         : Full-charge (regulation) voltage (V).
        i_precharge   : Current limit during pre-charge (A).
        i_fast        : Current limit during fast charge (A).
        i_term        : Termination threshold — done when Iout < i_term in
                        CV mode for _ITERM_CONSEC consecutive readings (A).
        capacity_ah        : Nominal pack capacity, used for Ah logging only (Ah).
        timeout_pre        : Pre-charge safety timeout (s). Fault if exceeded.
        timeout_fast       : Fast-charge safety timeout (s). Fault if exceeded.
        timeout_taper      : Taper safety timeout (s). Fault if exceeded.
        v_discharge_cutoff : Stop discharging when Vbat drops to this (V).
                             Hardware DPM (reverse_voltage) is also set
                             to this value as a backup protection.
        i_discharge        : Maximum current drawn from battery during
                             discharge (reverse_current) (A).
    '''
    def __init__(self, name,
                 v_min_input, v_cutoff, v_precharge, v_reg,
                 i_precharge, i_fast, i_term,
                 capacity_ah=0.0,
                 timeout_pre=3600, timeout_fast=18000, timeout_taper=7200,
                 v_discharge_cutoff=None, i_discharge=None):
        self.name        = name
        self.v_min_input = v_min_input
        self.v_cutoff    = v_cutoff
        self.v_precharge = v_precharge
        self.v_reg       = v_reg
        self.i_precharge = i_precharge
        self.i_fast      = i_fast
        self.i_term      = i_term
        self.capacity_ah = capacity_ah
        self.timeout_pre   = timeout_pre
        self.timeout_fast  = timeout_fast
        self.timeout_taper = timeout_taper
        # Discharge defaults: cutoff = v_cutoff, current = i_fast
        self.v_discharge_cutoff = v_discharge_cutoff if v_discharge_cutoff is not None else v_cutoff
        self.i_discharge        = i_discharge        if i_discharge        is not None else i_fast


# ---------------------------------------------------------------------------
# Built-in profiles
# ---------------------------------------------------------------------------

# 2S LiFePO4, 5 Ah (e.g. 6.4V nominal, 7.3V float)
LIFEPO4_2S_5AH = ChargingProfile(
    name='LiFePO4 2S 5Ah',
    v_min_input = 9.0,   # Minimum Vin to start charging (headroom above v_reg)
    v_cutoff    = 4.8,   # 2.4 V/cell — wait if battery is below this
    v_precharge = 5.0,   # 2.5 V/cell — transition to fast charge above
    v_reg       = 7.3,   # 3.65 V/cell — full charge / float voltage
    i_precharge = 0.25,  # 0.05 C
    i_fast      = 3.0,   # 0.6 C (recommended max)
    i_term      = 0.25,  # 0.05 C termination threshold
    capacity_ah = 5.0,
    timeout_pre   = 3600,   # 1 h
    timeout_fast  = 18000,  # 5 h
    timeout_taper = 7200,   # 2 h
    v_discharge_cutoff = 5.2,  # 2.6 V/cell — stop discharge above hard cutoff
    i_discharge        = 5.0,  # 1.0 C continuous discharge
)


# ---------------------------------------------------------------------------
# Charger state machine
# ---------------------------------------------------------------------------
class BatteryCharger:
    '''3-stage battery charger driven by periodic update() calls.

    Requires a BoardContext (from board.py) for hardware interaction.
    board.set_charger(c) calls start() automatically.

    The charger enters WAITING on start and polls until both Vin and Vbat
    conditions are met before enabling the converter.  FAULT (safety timeouts)
    auto-retries via WAITING after _FAULT_RETRY_S seconds.
    '''

    def __init__(self, profile):
        self.profile    = profile
        self._state     = STATE_IDLE
        self._stage_t   = 0      # time.time() when current stage started
        self._last_t    = 0      # time.time() of last update() call
        self._iterm_n   = 0      # consecutive below-i_term count
        self._charge_ah = 0.0   # accumulated charge delivered (Ah)
        self.fault_msg  = ''

    # --- Public API --------------------------------------------------------

    @property
    def state(self):
        return self._state

    @property
    def state_name(self):
        return _STATE_NAMES[self._state]

    def start(self, context):
        '''Enter WAITING state and begin polling for charge conditions.'''
        self._charge_ah = 0.0
        self._last_t    = time.time()
        self._iterm_n   = 0
        self.fault_msg  = ''
        self._enter_waiting()
        self._check_and_start(context)  # start immediately if conditions met

    def stop(self, context):
        '''Abort charging/discharging and disable the converter output.'''
        context.set('enabled', 0)
        context.set('reverse_enable', 0)
        self._state = STATE_IDLE
        print('Charger: stopped')

    def start_discharge(self, context, v_output):
        '''Begin discharging the battery into the VIN bus in reverse mode.

        The BQ25758 is placed in reverse mode: VOUT (battery) becomes the
        input and VIN becomes the output.

        Args:
            context  : BoardContext from board.py.
            v_output : Target VIN output voltage (V).  Set via
                       reverse_voltage (REG0x0C) — despite the name,
                       this register controls the VIN output voltage in
                       reverse mode (confirmed by testing).

        Discharge stops when Vbat < v_discharge_cutoff (software monitored).
        '''
        vout = context.get('vout')
        p = self.profile

        if vout < p.v_discharge_cutoff:
            print('Charger: battery {:.2f}V below discharge cutoff {:.2f}V'.format(
                vout, p.v_discharge_cutoff))
            return

        self.fault_msg = ''
        self._last_t   = time.time()

        print('Charger: discharge  vbat={:.2f}V  vout_target={:.2f}V  ilimit={:.2f}A'.format(
            vout, v_output, p.i_discharge))

        # reverse_voltage (REG0x0C) sets the VIN output voltage in
        # reverse mode (confirmed by testing — naming in datasheet is misleading).
        # Battery discharge cutoff is handled in software by update().
        context.set('reverse_voltage', v_output)
        context.set('reverse_current', p.i_discharge)
        context.set('reverse_enable', 1)
        context.set('enabled', 1)
        self._state   = STATE_DISCHARGE
        self._stage_t = time.time()

    def update(self, context):
        '''Advance the state machine.  Called every ~1 s from the poll loop.'''
        if self._state == STATE_IDLE:
            return

        now = time.time()

        # Accumulate delivered charge during active stages
        if self._state in (STATE_PRECHARGE, STATE_FAST, STATE_TAPER):
            dt = now - self._last_t
            if dt > 0:
                self._charge_ah += context.get('iout') * (dt / 3600.0)
            self._last_t = now

            # Check Vin is still present — pause to WAITING if it drops
            if context.get('vin') < self.profile.v_min_input:
                print('Charger: input voltage lost — waiting')
                context.set('enabled', 0)
                self._enter_waiting()
                return

        if self._state == STATE_DISCHARGE:
            dt = now - self._last_t
            if dt > 0:
                # In reverse mode iout reads battery current (VOUT side)
                self._charge_ah -= context.get('iout') * (dt / 3600.0)
            self._last_t = now
            if context.get('vout') < self.profile.v_discharge_cutoff:
                print('Charger: battery cutoff reached — discharge complete')
                context.set('enabled', 0)
                context.set('reverse_enable', 0)
                self._state = STATE_DONE
            return

        if self._state == STATE_WAITING:
            self._check_and_start(context)

        elif self._state == STATE_FAULT:
            if now - self._stage_t >= _FAULT_RETRY_S:
                print('Charger: retrying after fault')
                self._enter_waiting()
                self._check_and_start(context)

        elif self._state == STATE_PRECHARGE:
            if now - self._stage_t > self.profile.timeout_pre:
                self._fault(context, 'Pre-charge timeout')
                return
            if context.get('vout') >= self.profile.v_precharge:
                self._enter_fast(context)

        elif self._state == STATE_FAST:
            if now - self._stage_t > self.profile.timeout_fast:
                self._fault(context, 'Fast-charge timeout')
                return
            if context.get('regulation_mode') == 'CV':
                self._enter_taper(context)

        elif self._state == STATE_TAPER:
            if now - self._stage_t > self.profile.timeout_taper:
                self._fault(context, 'Taper timeout')
                return
            if context.get('iout') < self.profile.i_term:
                self._iterm_n += 1
                if self._iterm_n >= _ITERM_CONSEC:
                    self._enter_done(context)
            else:
                self._iterm_n = 0

    def get_summary(self):
        lines = [
            'Profile: {}'.format(self.profile.name),
            'State:   {}'.format(self.state_name),
            'Charge:  {:.3f} Ah'.format(self._charge_ah),
        ]
        if self.fault_msg:
            lines.append('Fault:   {}'.format(self.fault_msg))
        return '\n'.join(lines)

    # --- Internal ----------------------------------------------------------

    def _check_and_start(self, context):
        '''Start charging if Vin and Vbat conditions are both met.'''
        p = self.profile
        if context.get('vin') < p.v_min_input:
            return
        vout = context.get('vout')
        if vout < p.v_cutoff:
            return
        # Conditions met
        self._last_t = time.time()
        if vout < p.v_precharge:
            self._enter_precharge(context)
        else:
            self._enter_fast(context)

    def _enter_waiting(self):
        print('Charger: waiting for Vin and battery')
        self._state   = STATE_WAITING
        self._stage_t = time.time()

    def _enter_precharge(self, context):
        p = self.profile
        print('Charger: pre-charge  vout={:.2f}V  ilimit={:.2f}A'.format(
            context.get('vout'), p.i_precharge))
        context.set('output_voltage_limit', p.v_reg)
        context.set('output_current_limit', p.i_precharge)
        context.set('enabled', 1)
        self._state   = STATE_PRECHARGE
        self._stage_t = time.time()

    def _enter_fast(self, context):
        p = self.profile
        print('Charger: fast charge  vout={:.2f}V  ilimit={:.2f}A'.format(
            context.get('vout'), p.i_fast))
        context.set('output_voltage_limit', p.v_reg)
        context.set('output_current_limit', p.i_fast)
        context.set('enabled', 1)
        self._state   = STATE_FAST
        self._stage_t = time.time()

    def _enter_taper(self, context):
        # No limit change — converter is already at v_reg in CV mode
        print('Charger: taper  vout={:.2f}V  iout={:.2f}A'.format(
            context.get('vout'), context.get('iout')))
        self._iterm_n = 0
        self._state   = STATE_TAPER
        self._stage_t = time.time()

    def _enter_done(self, context):
        print('Charger: done  delivered={:.3f} Ah'.format(self._charge_ah))
        context.set('enabled', 0)
        self._state = STATE_DONE

    def _fault(self, context, msg):
        print('Charger FAULT:', msg)
        self.fault_msg = msg
        context.set('enabled', 0)
        self._state   = STATE_FAULT
        self._stage_t = time.time()
