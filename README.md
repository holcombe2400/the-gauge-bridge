# The Gauge Bridge

Connect a Vevor YT60234 weather station directly to [The Gauge](https://the-gauge.the-gauge.workers.dev), without a Weather Underground account.

## Install in Home Assistant

1. In The Gauge, create an account and open **Connect station**.
2. Create your connection code and keep the Station ID and relay secret handy.
3. In Home Assistant, open **Settings → Add-ons → Add-on Store**. Open the three-dot menu, select **Repositories**, and add:

   `https://github.com/holcombe2400/the-gauge-bridge`

4. Install **The Gauge Bridge**, paste in the connection details from The Gauge, then start it.
5. If you use Starlink, open the Starlink app and set **Settings → Router → Advanced → Custom DNS** to the Home Assistant IP address. The Bridge redirects only the Vevor upload address and forwards all normal lookups.
6. Follow the connection check in The Gauge to confirm the first reading.

## What it does

Vevor stations use a fixed Weather Underground-style upload address. The Bridge receives that local upload and forwards it securely to The Gauge. It never sends readings to Weather Underground and keeps only the most recent undelivered packet if your Internet connection drops.

See [the Bridge setup guide](gauge-bridge/README.md) for router and troubleshooting help.
