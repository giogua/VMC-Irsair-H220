# Irsap VMC (Irsair H 220) per Home Assistant

Integrazione custom per controllare le VMC **Irsap Irsair** (testata su Irsair H 220) tramite l'interfaccia web locale della macchina, senza cloud.

Ogni VMC diventa **un dispositivo** in Home Assistant con tutte le sue entità. Per aggiungere altre macchine basta ripetere la configurazione con un altro IP.

## Entità

| Tipo | Entità | Note |
|---|---|---|
| sensor | Temperatura esterna (Te), ripresa (Tr), espulsa (Tx), immissione (Ti) | dalla pagina principale |
| sensor | Efficienza recuperatore | calcolata: (Ti − Te) / (Tr − Te); non disponibile se Tr − Te < 2 °C |
| sensor | Giri ventilatore immissione / estrazione | dal menu *Stato* |
| sensor | Ore di funzionamento ventilatori | dal menu *Stato* (diagnostica) |
| sensor | Boost residuo, Allarmi | |
| binary_sensor | Bypass, Allarme, Antigelo batteria | |
| binary_sensor | Ventilatori da remoto | diagnostica, disattivati di default |
| number | Velocità ventilazione (%) | passi da 1 e 10 |
| number | Setpoint temperatura (°C) | passi da 0,2 e 2 |
| number | Durata boost (min) | impostando N minuti il boost parte, o viene corretto, per N minuti; 0 lo ferma |
| select | Stagione (Inverno / Estate) | *Parametri → Stagione* |
| switch | Accensione | on/off della macchina |
| switch | Boost | massima ventilazione per 10 minuti, poi torna alla velocità impostata |
| button | Aggiorna tutti i dati | forza la lettura del menu *Stato* e della stagione |

## Installazione (HACS)

1. HACS → ⋮ → *Repository personalizzati* → `https://github.com/giogua/VMC-Irsair-H220`, categoria **Integrazione**.
2. Installa **Irsap VMC (Irsair)** e riavvia Home Assistant.
3. *Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Irsap VMC*, poi inserisci l'IP della macchina (es. `192.168.1.243`) e un nome.

Opzioni: intervallo di aggiornamento dei valori principali (predefinito 30 s) e del menu Stato/Stagione (predefinito 300 s).

## Come funziona

L'interfaccia web della macchina non ha un'API: è composta da piccole pagine HTML, una per valore (`iftemp_e.html`, `ifspeed_sp.html`, …), e da form con pulsanti-immagine (`inc0001`, `dec0001`, `iic0001`, `ddc0001`, `tgl0001`, …).

- **Lettura**: le pagine della home si leggono senza effetti collaterali.
- **Comandi**: vengono simulati i click sui pulsanti +/−/++/−−/on-off, e ogni risposta contiene già il nuovo valore. Per impostare un valore preciso l'integrazione preme i pulsanti fino a raggiungerlo.
- **Menu (Stato, Parametri)**: si comporta come il display fisico, con un cursore lato server. L'integrazione lo naviga seguendo i link della pagina corrente, legge o modifica il valore e poi **riporta sempre il cursore alla Home**. Per questo il menu viene letto meno spesso.
- Tutte le richieste verso una macchina passano da un'unica coda, così non si sovrappongono. Tra due cambi di stagione consecutivi passano almeno 5 secondi.

## Sviluppo

```bash
pip install aiohttp pytest pytest-asyncio
pytest tests/test_api.py               # client contro una VMC simulata (tests/fake_vmc.py)

pip install pytest-homeassistant-custom-component
pytest -o asyncio_mode=auto tests/ha   # test end-to-end dentro Home Assistant
```
