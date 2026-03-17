# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
#
# Battery charger state machine for the BQ25758 bidirectional DC/DC converter.
#
# Implements a 3-stage CC/CV profile with pre-charge:
#   Pre-charge  : Vbat < v_precharge  → charge at i_precharge (low current)
#   Fast charge : Vbat >= v_precharge → charge at i_fast (CC mode)
#   Taper       : Vbat >= v_reg       → converter holds voltage (CV mode),
#                                        current tapers naturally
#   Done        : Iout < i_term for N consecutive readings → disable output
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

_STATE_NAMES = ('Idle', 'Pre', 'Fast', 'Taper', 'Done', 'Fault')


# ---------------------------------------------------------------------------
# Charging profile
# ---------------------------------------------------------------------------
class ChargingProfile:
    '''Parameters for a single battery chemistry / pack configuration.

    Args:
        name          : Human-readable label shown on display and in logs.
        v_cutoff      : Minimum safe battery voltage (V). Charging refused
                        below this — cell may be damaged.
        v_precharge   : Pre-charge to fast-charge transition voltage (V).
        v_reg         : Full-charge (regulation) voltage (V).
        i_precharge   : Current limit during pre-charge (A).
        i_fast        : Current limit during fast charge (A).
        i_term        : Termination threshold — done when Iout < i_term in
                        CV mode for ITERM_CONSEC consecutive readings (A).
        capacity_ah   : Nominal pack capacity, used for Ah logging only (Ah).
        timeout_pre   : Pre-charge safety timeout (s). Fault if exceeded.
        timeout_fast  : Fast-charge safety timeout (s). Fault if exceeded.
        timeout_taper : Taper safety timeout (s). Fault if exceeded.
    '''
    def __init__(self, name,
                 v_cutoff, v_precharge, v_reg,
                 i_precharge, i_fast, i_term,
                 capacity_ah=0.0,
                 timeout_pre=3600, timeout_fast=18000, timeout_taper=7200):
        self.name = name
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


# ---------------------------------------------------------------------------
# Built-in profiles
# ---------------------------------------------------------------------------

# 2S LiFePO4, 5 Ah (e.g. 6.4V nominal, 7.3V float)
LIFEPO4_2S_5AH = ChargingProfile(
    name='LiFePO4 2S 5Ah',
    v_cutoff    = 4.8,   # 2.4 V/cell — refuse to charge below this
    v_precharge = 5.0,   # 2.5 V/cell — transition to fast charge above
    v_reg       = 7.3,   # 3.65 V/cell — full charge / float voltage
    i_precharge = 0.25,  # 0.05 C
    i_fast      = 3.0,   # 0.6 C (recommended max)
    i_term      = 0.25,  # 0.05 C termination threshold
    capacity_ah = 5.0,
    timeout_pre   = 3600,   # 1 h
    timeout_fast  = 18000,  # 5 h
    timeout_taper = 7200,   # 2 h
)


# ---------------------------------------------------------------------------
# Charger state machine
# ---------------------------------------------------------------------------
class BatteryCharger:
    '''3-stage battery charger driven by periodic update() calls.

    Requires a BoardContext (from board.py) for hardware interaction.
    Call start() once to begin charging, then update() every ~1 s.
    '''

    # Number of consecutive readings below i_term to declare DONE
    _ITERM_CONSEC = const(5)

    def __init__(self, profile):
        self.profile = profile
        self._state      = STATE_IDLE
        self._stage_t    = 0      # time.time() when current stage started
        self._last_t     = 0      # time.time() of last update() call
        self._iterm_n    = 0      # consecutive below-i_term count
        self._charge_ah  = 0.0   # accumulated charge delivered (Ah)
        self.fault_msg   = ''

    # --- Public API --------------------------------------------------------

    @property
    def state(self):
        return self._state

    @property
    def state_name(self):
        return _STATE_NAMES[self._state]

    def start(self, context):
        '''Begin a charge cycle. Reads Vout to pick the initial stage.'''
        vout = context.get('vout')
        p = self.profile

        if vout < p.v_cutoff:
            self._fault(context,
                'Battery {:.2f}V below cutoff {:.2f}V'.format(vout, p.v_cutoff))
            return

        self._charge_ah = 0.0
        self._last_t    = time.time()
        self._iterm_n   = 0
        self.fault_msg  = ''

        if vout < p.v_precharge:
            self._enter_precharge(context)
        else:
            self._enter_fast(context)

    def stop(self, context):
        '''Abort charging and disable the converter output.'''
        context.set('enabled', 0)
        self._state = STATE_IDLE
        print('Charger: stopped')

    def update(self, context):
        '''Advance the state machine.  Call every ~1 s from the poll loop.'''
        if self._state in (STATE_IDLE, STATE_DONE, STATE_FAULT):
            return

        now = time.time()
        dt  = now - self._last_t
        if dt > 0:
            iout = context.get('iout')
            self._charge_ah += iout * (dt / 3600.0)
            self._last_t = now

        vout    = context.get('vout')
        iout    = context.get('iout')
        elapsed = now - self._stage_t
        p       = self.profile

        if self._state == STATE_PRECHARGE:
            if elapsed > p.timeout_pre:
                self._fault(context, 'Pre-charge timeout')
                return
            if vout >= p.v_precharge:
                self._enter_fast(context)

        elif self._state == STATE_FAST:
            if elapsed > p.timeout_fast:
                self._fault(context, 'Fast-charge timeout')
                return
            if context.get('regulation_mode') == 'CV':
                self._enter_taper(context)

        elif self._state == STATE_TAPER:
            if elapsed > p.timeout_taper:
                self._fault(context, 'Taper timeout')
                return
            if iout < p.i_term:
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

    # --- Stage transitions -------------------------------------------------

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
        self._state = STATE_FAULT
