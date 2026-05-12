# WireGuard split-tunnel: развёртывание с нуля

> **Когда применять:** prod-сервер (или dev-VPS, если он переедет обратно в локацию, где блочится Telegram) теряет связь с `api.telegram.org` из-за провайдер-уровневой блокировки. Решение — проброс исходящего трафика **только к подсетям Telegram** через WG-туннель к выходной ноде в нейтральной локации, остальной трафик идёт напрямую.
>
> **Текущий статус (2026-05-12):** runbook **не активирован** — после переезда dev VPS на Frankfurt (см. [ADR-0009](../adr/0009-dev-vps-frankfurt.md)) листенер ходит к Telegram напрямую. Документ сохранён для (1) prod-варианта если prod-VPS будет в РФ, (2) backup-сценария при бане текущего exit-IP.

Пошаговое руководство. Воспроизводит конфигурацию `prod.vizor` (клиент, за блокировкой) ↔ `proxy.vizor` (сервер, нейтральная локация).

Реальные IP, ключи и подсети — в GitHub Secrets / memory, **не в репо** (правило 2 [`CLAUDE.md`](../../CLAUDE.md)). Этот документ — только процедура.

## Содержание

1. [Архитектура](#архитектура)
2. [Шаг 1. WG-сервер на VPS-выходе](#шаг-1-wg-сервер-на-vps-выходе)
3. [Шаг 2. WG-клиент на хосте за блокировкой](#шаг-2-wg-клиент-на-хосте-за-блокировкой)
4. [Шаг 3. Связать сервер и клиента](#шаг-3-связать-сервер-и-клиента)
5. [Шаг 4. Smoke-проверки](#шаг-4-smoke-проверки)
6. [Шаг 5. Cron автообновления подсетей AS62041](#шаг-5-cron-автообновления-подсетей-as62041)
7. [Грабли](#грабли)

---

## Архитектура

```
   [контейнеры, host] ──┐
                        ▼                        UDP 51820
                 ┌─────────────┐  encrypted   ┌──────────────┐
                 │   wg0       │ ────────────►│   wg0        │
                 │ 10.99.99.2  │              │ 10.99.99.1   │
                 │ (client)    │              │ (server +    │
                 └─────────────┘              │  MASQUERADE) │
                        ▲                     └──────┬───────┘
                        │                            │
                       host                        WAN iface
                  (за блокировкой)              (нейтральная локация)
                                                     │
                                                     ▼
                                              api.telegram.org
```

Ядро на клиенте автоматически роутит к Telegram-подсетям через `wg0`, всё остальное идёт напрямую через провайдера хоста. Это split-tunnel, не full-tunnel.

---

## Шаг 1. WG-сервер на VPS-выходе

На свежем Ubuntu 24.04 в нейтральной локации, под `root`:

```bash
# 1. Установка пакета
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq wireguard-tools

# 2. Включить IP forwarding persistently
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-wireguard.conf
sysctl -p /etc/sysctl.d/99-wireguard.conf
# verify: должно быть `net.ipv4.ip_forward = 1`

# 3. Сгенерировать пару ключей сервера
umask 077
mkdir -p /etc/wireguard
cd /etc/wireguard
wg genkey | tee server_private.key | wg pubkey > server_public.key

# 4. Узнать имя WAN-интерфейса (нужно для MASQUERADE)
ip route get 1.1.1.1 | awk '{print $5; exit}'
# proxy.vizor → ens3; у других провайдеров может быть eth0/eno1/...

# 5. Записать /etc/wireguard/wg0.conf
WAN_IFACE=ens3   # ← подставить вывод предыдущей команды
SERVER_PRIV=$(cat /etc/wireguard/server_private.key)
cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address    = 10.99.99.1/24
ListenPort = 51820
PrivateKey = $SERVER_PRIV
PostUp   = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -A FORWARD -o wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o $WAN_IFACE -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -D FORWARD -o wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o $WAN_IFACE -j MASQUERADE

# [Peer] клиента добавится в Шаге 3 (после генерации client_public.key).
EOF
chmod 600 /etc/wireguard/wg0.conf

# 6. Открыть порты в ufw (если активен) — обязательно `22/tcp` чтобы не потерять SSH
ufw allow 22/tcp comment "ssh"
ufw allow 51820/udp comment "wireguard"

# 7. Поднять туннель
systemctl enable --now wg-quick@wg0
wg show

# 8. Выписать публичный ключ сервера — нужен на клиенте в Шаге 2
cat /etc/wireguard/server_public.key
```

---

## Шаг 2. WG-клиент на хосте за блокировкой

На сервере, исходящие соединения которого к Telegram режутся, под `root`:

```bash
# 1. Установка пакета
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq wireguard-tools

# 2. Сгенерировать пару ключей клиента
umask 077
mkdir -p /etc/wireguard
cd /etc/wireguard
wg genkey | tee client_private.key | wg pubkey > client_public.key

# 3. Записать /etc/wireguard/wg0.conf
# AllowedIPs пока стартовый (широкие подсети); Шаг 5 заменит на актуальный из BGP AS62041.
SERVER_PUB="<значение cat /etc/wireguard/server_public.key из Шага 1.8>"
SERVER_ENDPOINT="<VPS-IP>:51820"
CLIENT_PRIV=$(cat /etc/wireguard/client_private.key)
cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address    = 10.99.99.2/24
PrivateKey = $CLIENT_PRIV

[Peer]
PublicKey           = $SERVER_PUB
Endpoint            = $SERVER_ENDPOINT
AllowedIPs          = 10.99.99.0/24, 91.108.0.0/16, 149.154.160.0/20, 185.76.151.0/24
PersistentKeepalive = 25
EOF
chmod 600 /etc/wireguard/wg0.conf

# 4. Выписать публичный ключ клиента — нужен на сервере в Шаге 3
cat /etc/wireguard/client_public.key
```

> **`10.99.99.0/24` в `AllowedIPs` обязательно** — без него `ping 10.99.99.1` и `traceroute` через туннель не пройдут (kernel WG отбрасывает пакет к адресату, не входящему в `AllowedIPs` пира с ошибкой `Required key not available`). Реальный трафик к Telegram при этом всё равно работал бы, но диагностика была бы кривой.

---

## Шаг 3. Связать сервер и клиента

На **сервере** — добавить peer-секцию с client pubkey и сделать hot-reload:

```bash
CLIENT_PUB="<значение из Шага 2.4>"
cat >> /etc/wireguard/wg0.conf <<EOF

[Peer]
# имя хоста за блокировкой
PublicKey  = $CLIENT_PUB
AllowedIPs = 10.99.99.2/32
EOF

# Hot-reload без рестарта systemd unit (на сервере достаточно — peer'у только один /32)
wg syncconf wg0 <(wg-quick strip wg0)
wg show
```

На **клиенте** — поднять туннель:

```bash
systemctl enable --now wg-quick@wg0
sleep 2
wg show     # `latest handshake` появится через ~1 сек после первого исходящего пакета
```

---

## Шаг 4. Smoke-проверки

На клиенте:

```bash
# Туннель живой
wg show wg0                                    # `latest handshake: N seconds ago`
ping -c 2 10.99.99.1                           # RTT ≈ latency до VPS

# Маршруты: Telegram идёт через wg0, остальное — нет
ip route get 149.154.166.110                   # dev wg0 src 10.99.99.2
ip route get 8.8.8.8                           # dev <WAN_IFACE> (НЕ wg0)

# TCP до Telegram открыт
nc -zv 149.154.166.110 443                     # open
curl --connect-timeout 5 -sI https://api.telegram.org/   # HTTP/2 302

# Из Docker-контейнера, которому Telegram нужен
docker exec <container> wget --timeout=5 -qO- https://api.telegram.org/ | head -c 100
```

Если что-то не сходится — см. [Грабли](#грабли).

---

## Шаг 5. Cron автообновления подсетей AS62041

Подсети Telegram меняются редко, но иногда добавляются новые блоки (наш стартовый широкий список `91.108.0.0/16` это покрывает, но точечный список из BGP надёжнее). Скрипт раз в месяц синхронизирует `AllowedIPs` с BGP AS62041 через RADB whois.

На WG-клиенте, под `root`:

```bash
# 1. whois для опроса RADB
apt-get install -y -qq whois

# 2. Скрипт
cat > /usr/local/bin/update-telegram-routes.sh <<'SH'
#!/usr/bin/env bash
# Обновляет AllowedIPs в /etc/wireguard/wg0.conf из BGP-роутов AS62041 (Telegram).
# Безопасно: при пустом/подозрительном ответе whois — оставляет текущую конфигурацию.
# Reload через `systemctl restart wg-quick@wg0` (короткий разрыв <1 с). Routing
# table обновляется только полным рестартом — `wg syncconf` её не трогает.
set -euo pipefail

WG_CONF=/etc/wireguard/wg0.conf
WG_IFACE=wg0
TUNNEL_NET=10.99.99.0/24
TAG=update-telegram-routes

log() { logger -t "$TAG" -- "$*"; printf "%s\n" "$*" >&2; }

ROUTES=$(whois -h whois.radb.net -- "-i origin AS62041" 2>/dev/null \
  | awk "/^route:/{print \$2}" \
  | sort -V -u)

if [ -z "$ROUTES" ]; then
  log "WARN: whois вернул пустой результат, AllowedIPs не трогаем"
  exit 0
fi

SANITY=$(printf "%s\n" "$ROUTES" | grep -cE "^(91\.108\.|149\.154\.|185\.76\.|95\.161\.|91\.105\.)" || true)
if [ "$SANITY" -lt 3 ]; then
  log "WARN: подозрительный результат whois (sanity=$SANITY), AllowedIPs не трогаем"
  exit 0
fi

NEW_LIST=$(printf "%s\n" "$ROUTES" | paste -sd, - | sed "s/,/, /g")
NEW_LINE="AllowedIPs = $TUNNEL_NET, $NEW_LIST"
CUR_LINE=$(grep "^AllowedIPs" "$WG_CONF" | head -1)

if [ "$CUR_LINE" = "$NEW_LINE" ]; then
  log "Без изменений ($(printf "%s\n" "$ROUTES" | wc -l) подсетей)"
  exit 0
fi

sed -i "s|^AllowedIPs.*|$NEW_LINE|" "$WG_CONF"
systemctl restart wg-quick@"$WG_IFACE"
log "Обновлено: $(printf "%s\n" "$ROUTES" | wc -l) подсетей, hot-reload OK"
SH
chmod +x /usr/local/bin/update-telegram-routes.sh

# 3. systemd service (oneshot)
cat > /etc/systemd/system/update-telegram-routes.service <<EOF
[Unit]
Description=Update Telegram subnets in WireGuard AllowedIPs
After=wg-quick@wg0.service
Requires=wg-quick@wg0.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/update-telegram-routes.sh
EOF

# 4. systemd timer (monthly + catch-up при простое)
cat > /etc/systemd/system/update-telegram-routes.timer <<EOF
[Unit]
Description=Monthly Telegram subnets refresh

[Timer]
OnCalendar=monthly
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now update-telegram-routes.timer

# 5. Первый прогон сразу — чтобы заменить стартовый широкий список на актуальный из BGP
systemctl start update-telegram-routes.service
journalctl -u update-telegram-routes.service -n 20 --no-pager
grep AllowedIPs /etc/wireguard/wg0.conf      # должно быть ~15 подсетей
```

После этого `AllowedIPs` будет всегда отражать актуальный список подсетей AS62041, обновляясь раз в месяц без участия человека.

Принудительный прогон в любой момент:

```bash
systemctl start update-telegram-routes.service && journalctl -u update-telegram-routes.service -n 20
```

---

## Грабли

- **`Required key not available` при `ping 10.99.99.1`** — на клиенте в `AllowedIPs` нет `10.99.99.0/24` (или хотя бы `/32` сервера). Kernel WG отбрасывает пакеты к адресату вне `AllowedIPs` пира. Добавить туннельную подсеть в `AllowedIPs` и сделать `systemctl restart wg-quick@wg0`.
- **Handshake не появляется** — UDP 51820 закрыт на стороне сервера (cloud security group / ufw / iptables INPUT), либо `Endpoint` в клиентском конфиге неверный, либо сетевой провайдер режет UDP. На клиенте `wg show` покажет `(none)` в latest handshake. Проверить: `nc -uvz <vps-ip> 51820` с клиента (вернёт `succeeded` если хотя бы один пакет ушёл; UDP без ответа определять сложнее — лучше смотреть на сервере `tcpdump -ni any udp port 51820`).
- **`wg syncconf` не обновляет routing table** — он трогает только peer-config внутри kernel-модуля WG. Если изменился список `AllowedIPs` на клиенте — kernel-роуты под новые подсети не добавятся, пакеты пойдут мимо туннеля. Для применения нужен полный `systemctl restart wg-quick@wg0` (короткий разрыв ≤1 с). Поэтому скрипт автообновления делает именно restart, а не syncconf.
- **Маршрут через wg0 для одного IP не работает, для других в той же подсети — работает** — этот IP не отвечает по `nc`/`ICMP` со стороны Telegram (например, сервисный IP, не endpoint). Это не проблема туннеля. Проверять на endpoint-IP вроде `149.154.166.110`/`149.154.167.50`.
- **traceroute показывает только первый хоп `10.99.99.1`** — нормально для Telegram (на их стороне ICMP/TCP TTL responses гасятся). Главное что endpoint отвечает.
- **MTU**. WireGuard добавляет накладные расходы; иногда дефолтный MTU 1500 в хост-интерфейсе ломает большие пакеты (TLS handshake может застрять). Если бывают странные таймауты на больших ответах — попробовать `MTU = 1420` в `[Interface]` на клиенте. По умолчанию `wg-quick` ставит безопасное значение, обычно проблема не возникает.
- **`/etc/sysctl.d/99-wireguard.conf` не применился после reboot** — проверить `sysctl net.ipv4.ip_forward`. Persistent через `/etc/sysctl.d/*.conf` должен работать; если нет — добавить `sysctl --system` в `PostUp` или в `/etc/rc.local`.
- **`wg-quick@wg0.service` падает с `RTNETLINK answers: File exists`** — интерфейс `wg0` уже создан вручную/предыдущей попыткой. `ip link del wg0` и `systemctl restart wg-quick@wg0`.
