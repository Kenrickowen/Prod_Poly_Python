# Docker Runbook

This runs the Polymarket bot with the FastAPI dashboard exposed on port `8080`.

## Local Build

```bash
cd /Users/frederickmarvel/PolyRustBot/Prod_Poly_Python
docker compose up -d --build
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

## Remote Server

Copy the project to the server, then create `.env` on the server with your real wallet/API/RPC values. Do not bake `.env` into the image.

```bash
cd Prod_Poly_Python
docker compose up -d --build
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
