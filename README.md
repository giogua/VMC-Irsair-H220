<p align="center">
  <img src="images/logo.png" alt="Irsap" height="72">
</p>

# Irsap VMC (Irsair H 220) for Home Assistant

Custom integration to monitor and control **Irsap Irsair** mechanical ventilation units with heat recovery (*VMC*, tested on the Irsair H 220) through the unit's local web interface. No cloud required.

Each unit shows up as **one device** that holds all of its entities. To add more units, run the setup again with another IP address.

## Entities

| Platform | Entity | Notes |
|---|---|---|
| sensor | Outdoor (Te), extract (Tr), exhaust (Tx) and supply (Ti) air temperature | from the main page |
| sensor | Heat recovery efficiency | computed as (Ti − Te) / (Tr − Te); unavailable when Tr − Te < 2 °C |
| sensor | Supply / extract fan speed (rpm) | from the unit's status menu |
| sensor | Fan operating hours | from the status menu (diagnostic) |
| sensor | Boost remaining, Alarms | |
| binary_sensor | Bypass, Alarm, Coil antifreeze | |
| binary_sensor | Supply / extract fan remote control | diagnostic, disabled by default |
| number | Fan speed (%) | steps of 1 and 10 |
| number | Temperature set point (°C) | steps of 0.2 and 2 |
| number | Boost duration (min) | setting N starts the boost, or adjusts a running one, for N minutes; 0 stops it |
| select | Season (winter / summer) | the unit's *Parameters → Season* setting |
| switch | Power | turns the unit on and off |
| switch | Boost | maximum ventilation for 10 minutes, then back to the configured speed |
| button | Refresh all data | forces a read of the status menu and the season |

Entity names are translated: English by default, Italian when Home Assistant runs in Italian.

## Installation (HACS)

1. HACS → ⋮ → *Custom repositories* → `https://github.com/giogua/VMC-Irsair-H220`, category **Integration**.
2. Install **Irsap VMC (Irsair)** and restart Home Assistant.
3. *Settings → Devices & services → Add integration → Irsap VMC*, then enter the unit's IP address (e.g. `192.168.1.243`) and a name.

Options: refresh interval for the main values (default 30 s) and for the status menu and season (default 300 s).

## How it works

The unit's web interface has no API. It is made of tiny HTML pages, one per value (`iftemp_e.html`, `ifspeed_sp.html`, …), and forms with image buttons (`inc0001`, `dec0001`, `iic0001`, `ddc0001`, `tgl0001`, …).

- **Reading**: the main page widgets can be read without side effects.
- **Commands**: the integration simulates clicks on the +, −, ++, −− and on/off buttons. Every response already contains the new value. To reach an exact value it keeps pressing until the target is reached.
- **Menu** (status, parameters): it behaves like the physical display, with a server-side cursor. The integration navigates it by following the links of the current page, reads or changes the value, and then **always brings the cursor back to the home page**. That is why the menu is polled less often.
- All requests to a unit go through a single queue, so they never overlap. Two consecutive season changes are always at least 5 seconds apart.

## Development

```bash
pip install aiohttp pytest pytest-asyncio
pytest tests/test_api.py               # client against a simulated unit (tests/fake_vmc.py)

pip install pytest-homeassistant-custom-component
pytest -o asyncio_mode=auto tests/ha   # end-to-end tests inside Home Assistant
```

## Disclaimer

This is an unofficial, community project. It is not affiliated with or endorsed by Irsap S.p.A. The Irsap name and logo are trademarks of their owner and are used only to identify the supported devices.
