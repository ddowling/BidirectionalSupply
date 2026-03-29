# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
#
# Battery State of Charge estimator.
#
# Uses coulomb counting as the primary tracking method, anchored by:
#   - OCV-SOC table lookup when current has been near zero for rest_time_s seconds
#   - Explicit anchor() calls at known endpoints (e.g. 100% at charge completion)
#
# NOTE: LiFePO4 has a very flat OCV plateau (20–80% SOC ≈ 6.56–6.64 V for 2S),
# so OCV alone carries ±15–20% uncertainty in the mid-range.  Coulomb counting
# after an anchor at STATE_DONE is the accurate path; OCV is used to bootstrap
# SOC on startup before any charge cycle has completed.
#
# Usage:
#   est = SocEstimator(capacity_ah=5.0, ocv_table=MY_TABLE)
#   est.tick(vbat, ibat)   # ibat positive=charging, negative=discharging
#   est.anchor(100.0)      # call at known SOC points
#   est.get_soc_str()      # '67%' or '??' if unknown

import time


class SocEstimator:
    '''Battery State of Charge estimator using coulomb counting with OCV anchoring.

    Args:
        capacity_ah    : Nominal battery capacity (Ah).
        ocv_table      : Sequence of (voltage_V, soc_pct) pairs sorted by
                         voltage ascending.  Used for rest-state SOC lookup.
        rest_threshold : Current magnitude below which battery is considered
                         at rest for OCV measurement (A).
        rest_time_s    : Seconds continuously below rest_threshold before an
                         OCV anchor is applied.
    '''

    def __init__(self, capacity_ah, ocv_table,
                 rest_threshold=0.05, rest_time_s=120):
        self._capacity_ah = capacity_ah
        self._ocv_table   = ocv_table
        self._rest_thresh = rest_threshold
        self._rest_time   = rest_time_s

        self._soc    = None  # None until first anchor
        self._rest_s = 0     # seconds continuously at rest
        self._last_t = None  # time.time() of last tick()

    # --- Public API --------------------------------------------------------

    def tick(self, vbat, ibat):
        '''Advance the estimator.  Called once per update cycle (~1 s).

        Args:
            vbat : Battery terminal voltage (V) — context.get('vout')
            ibat : Battery current (A), positive=charging, negative=discharging
        '''
        now = time.time()

        if self._last_t is None:
            self._last_t = now
            # Attempt immediate OCV anchor on first call if the battery is at rest
            if abs(ibat) < self._rest_thresh:
                soc = self._ocv_lookup(vbat)
                if soc is not None:
                    self._soc = soc
            return

        dt = now - self._last_t
        self._last_t = now

        if dt <= 0:
            return

        # --- Coulomb counting ---
        if self._soc is not None:
            delta = (ibat * dt / 3600.0) / self._capacity_ah * 100.0
            self._soc += delta
            if self._soc < 0.0:
                self._soc = 0.0
            elif self._soc > 100.0:
                self._soc = 100.0

        # --- OCV rest anchoring ---
        if abs(ibat) < self._rest_thresh:
            self._rest_s += dt
            if self._rest_s >= self._rest_time:
                soc = self._ocv_lookup(vbat)
                if soc is not None:
                    self._soc = soc
                self._rest_s = 0  # reset to avoid repeated anchoring each second
        else:
            self._rest_s = 0

    def anchor_ocv(self, vbat):
        '''Anchor SOC from OCV table without requiring a rest period.

        Use only when the battery is known to be at rest (e.g. just before
        charging starts).  Does nothing if SOC is already known — coulomb
        counting is more accurate than OCV on the flat LiFePO4 plateau.
        '''
        if self._soc is not None:
            return
        soc = self._ocv_lookup(vbat)
        if soc is not None:
            self._soc    = soc
            self._rest_s = 0

    def anchor(self, soc_pct):
        '''Force SOC to a known value.

        Call at charge completion (anchor(100.0)) or after a verified full
        discharge (anchor(0.0)).  Also resets the rest timer.
        '''
        if soc_pct < 0.0:
            soc_pct = 0.0
        elif soc_pct > 100.0:
            soc_pct = 100.0
        self._soc    = soc_pct
        self._rest_s = 0

    def get_soc(self):
        '''Return SOC as float 0.0–100.0, or None if not yet known.'''
        return self._soc

    def get_soc_str(self):
        '''Return SOC as a short display string: "67%" or "??" if unknown.'''
        if self._soc is None:
            return '??'
        return '{:.0f}%'.format(self._soc)

    # --- Internal ----------------------------------------------------------

    def _ocv_lookup(self, voltage):
        '''Linear interpolation of SOC from OCV table.'''
        t = self._ocv_table
        if not t:
            return None
        if voltage <= t[0][0]:
            return float(t[0][1])
        if voltage >= t[-1][0]:
            return float(t[-1][1])
        for i in range(1, len(t)):
            v0, s0 = t[i - 1]
            v1, s1 = t[i]
            if v0 <= voltage <= v1:
                frac = (voltage - v0) / (v1 - v0)
                return s0 + frac * (s1 - s0)
        return None
