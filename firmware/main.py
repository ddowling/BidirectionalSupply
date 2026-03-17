# Copyright (c) 2026 Denis Dowling (dpd@opsol.com.au)
import board
from display import display_error


def _load_role(filename='role.dat'):
    '''Read role.dat and initialise the board role.

    Supported roles:
        role=converter   — general-purpose DC/DC converter (default).
                           startup.dat provides voltage/current limits.
        role=charger     — battery charger. Requires a profile= line
                           naming a ChargingProfile from charger.py.

    Example role.dat for charger:
        role=charger
        profile=LIFEPO4_2S_5AH

    Lines beginning with # are comments. Unknown keys are ignored.
    If role.dat is absent the board defaults to converter mode.
    '''
    try:
        with open(filename, 'r') as f:
            lines = f.read().splitlines()
    except OSError:
        return  # No role.dat — default converter behaviour

    params = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            k, _, v = line.partition('=')
            params[k.strip()] = v.strip()

    role = params.get('role', 'converter')
    print(f'Role: {role}')

    if role == 'charger':
        import charger as _charger
        profile_name = params.get('profile', '')
        profile = getattr(_charger, profile_name, None)
        if profile is None:
            raise ValueError(f'role.dat: unknown profile: {profile_name!r}')
        print(f'Charger profile: {profile.name}')
        board.set_charger(_charger.BatteryCharger(profile))

    elif role == 'converter':
        pass  # startup.dat already applied by load_startup()

    else:
        raise ValueError(f'role.dat: unknown role: {role!r}')


board.monitor(True)

try:
    board.setup()
    board.load_startup()
    _load_role()

except Exception as e:
    display_error(str(e))
