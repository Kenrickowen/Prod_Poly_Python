# Docker Runbook

This runs the Polymarket bot with the FastAPI dashboard exposed on port `8080`.

## Local Build

```bash
cd /Users/frederickmarvel/PolyRustBot/Prod_Poly_Python
docker compose up -d --build
```

If your server says `unknown shorthand flag: 'd' in -d`, it probably does not have the Docker Compose plugin installed. Use the legacy command if it exists:

```bash
docker-compose up -d --build
```

Or install the Compose plugin on Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y docker-compose-plugin
docker compose version
```

Open:

```text
http://localhost:8080
```

Logs:

```bash
docker compose logs -f polymarket-bot
```

Stop:

```bash
docker compose down
```

## Safe Dashboard Test

Use the simulation dashboard to test the web UI without trading, wallet signing, or real redemption.

Docker Compose v2:

```bash
docker compose --profile sim up -d --build dashboard-sim
```

Legacy Docker Compose:

```bash
docker-compose --profile sim up -d --build dashboard-sim
```

Open:

```text
http://localhost:8082
```

This service runs `run_sim_dashboard.py`, uses fake balances/trades, and exposes the `Redeem Bets` button against simulated data only. The normal command below still runs the real bot as usual:

```bash
docker-compose up -d --build
```

## Remote Server

Copy the project to the server, then create `.env` on the server with your real wallet/API/RPC values. Do not bake `.env` into the image.

```bash
cd Prod_Poly_Python
docker compose up -d --build
```

If `docker compose` is unavailable, use:

```bash
docker-compose up -d --build
```

If the server has a firewall, allow TCP `8080`, or put this behind a reverse proxy/VPN.

## Persistent Data

`docker-compose.yml` stores bot runtime data in the named Docker volume `bot-data`.

This includes:

- `trade_history.csv`
- `position_size.json`, saved when you change position size in the dashboard

Inspect the volume:

```bash
docker compose exec polymarket-bot ls -la /app/data
```

## Updating

```bash
docker compose down
docker compose up -d --build
```

The `bot-data` volume is kept unless you explicitly remove it with:

```bash
docker compose down -v
```
