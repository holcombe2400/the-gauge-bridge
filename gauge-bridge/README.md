# The Gauge Bridge

The Gauge Bridge is a small local helper for Vevor YT60234 stations. It receives the station's normal upload on your home or farm network and sends the reading straight to The Gauge. You do **not** need a Weather Underground account.

## Before you start

- A Home Assistant installation with the Add-on Store.
- Your Vevor station and Home Assistant on the same local network.
- The connection details created in **The Gauge → Settings → Connect your station**.

## Setup

1. Install **The Gauge Bridge** and open its **Configuration** tab.
2. Paste the Gauge URL, Station ID, and relay secret from The Gauge. Leave the update interval at 60 seconds.
3. Start the Bridge and set it to start automatically.
4. Give Home Assistant a reserved/fixed local IP address in your router.
5. In the router's local DNS settings, point `rtupdate.wunderground.com` to that Home Assistant IP address.
6. Open the Vevor console at `http://192.168.1.1`. In its Weather Underground panel, enter the Station ID and relay secret from The Gauge, then save.
7. Return to The Gauge and select **Check my connection**. A green result confirms the first reading.

## If it does not connect

Open `http://HOME_ASSISTANT_IP/health` in a browser on the same network.

- `lastStationPacketAt` empty: the station has not reached the Bridge. Recheck the router DNS override and the Vevor Station ID/key.
- `lastStationPacketAt` present but `lastDeliveredAt` empty: the Bridge received the station but could not reach The Gauge. Check the Gauge URL and Internet connection.
- `queued: true`: the newest reading is being kept safely and will retry automatically.

The Bridge stores only the latest undelivered packet locally. It never sends readings to Weather Underground.
