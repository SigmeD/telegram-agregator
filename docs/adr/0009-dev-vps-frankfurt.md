# ADR-0009: Dev VPS перенесён в Frankfurt; WireGuard split-tunnel пока не активирован

- **Статус:** Accepted
- **Дата:** 2026-05-12
- **Авторы:** Максим Ерохин

## Контекст

До 2026-05-12 dev-окружение бэкенда деплоилось на `user1@87.242.87.8` (Ubuntu 22.04.5, российский хостер, см. [`CLAUDE.md`](../../CLAUDE.md) ранее). В этой локации исходящий трафик к `api.telegram.org` нестабилен (часть подсетей Telegram блочится провайдером или RKN). Изначальный план (см. [`wireguard-split-tunnel.md`](../runbook/wireguard-split-tunnel.md)) — обойти блокировку через WG-туннель к выходной ноде `proxy.vizor` в нейтральной локации.

В процессе FEATURE-03 manual smoke 2026-05-12 обнаружилось:
- WG-сервер уже арендован у FirstByte в Франкфурте (`vpn.vpn.vpn` = `95.81.94.83`, Ubuntu 24.04.2, KVM-SSD-1-FRA 429 RUB/мес).
- WG-клиент на исходном `87.242.87.8` ещё не настроен (split-tunnel не работает).
- Bootstrap и `backend-listener` запустили напрямую на Frankfurt-узле — Telethon ходит к `api.telegram.org` без посредника, всё работает.

Стоимость и сложность операций: единственная инфраструктура в Frankfurt (без WG) проще одной российской + WG-связки на двух хостах. Risk-profile: Telegram банит по поведению + telephone-фингерпринту, не по геолокации исходящего IP — Frankfurt vs Россия здесь не критичны.

## Решение

**Dev VPS бэкенда — `user1@95.81.94.83` (Frankfurt, FirstByte) насовсем.** Российский VPS `user1@87.242.87.8` выводится из dev-цепочки.

WireGuard split-tunnel **остаётся в репо** ([`docs/runbook/wireguard-split-tunnel.md`](../runbook/wireguard-split-tunnel.md)) как готовая процедура для:
- **Prod-варианта**, если prod-VPS будет размещён в РФ (например ради ФЗ-152 / резидентности данных). Тогда prod-VPS = WG-клиент, отдельная exit-нода = WG-сервер.
- **Backup-сценария**, если текущий Frankfurt exit-IP `95.81.94.83` забанят на стороне Telegram — поднять параллельную exit-ноду в другой нейтральной локации, переключить через WG за минуты.

GitHub Secrets `DEV_VPS_HOST` / `DEV_VPS_USER` (используются в `cd-backend-dev.yml`) обновляются на новые значения.

## Рассмотренные альтернативы

- **Оставить dev на `87.242.87.8`, поднять WG к Frankfurt по runbook.** Отвергнута: две машины вместо одной, дополнительная точка отказа (WG handshake), сложнее CI deploy-target (через bastion или с дополнительным маршрутом). При том что Frankfurt VPS уже арендован и стабильно ходит к Telegram напрямую, WG здесь — лишний слой без выгоды.
- **Перенести dev на западный hyperscaler (Hetzner / DigitalOcean / OVH).** Отвергнута: 429 RUB/мес у FirstByte против $5+/мес у западных провайдеров; оплата валютой проще через российский биллинг; SLA для dev-окружения не критичен.
- **Использовать управляемый Telegram-аккаунт через cloud Telethon-as-service.** Отвергнута: ТЗ FEATURE-10 требует user-session под нашим контролем (ADR-0003); cloud-провайдер = доверенная сторона с доступом к session-файлу.

## Последствия

- **Позитивные.**
  - Один VPS вместо двух, ниже расходы и поверхность атаки.
  - `api.telegram.org` доступен напрямую без WG handshake / MTU-тюнинга / роутинг-перезагрузки.
  - Frankfurt = жёсткий GDPR-периметр (плюс для PII лидов; ТЗ разд. 9).
- **Негативные.**
  - Если Telegram забанит исходящий IP `95.81.94.83`, перезапуск через WG к другому exit-IP требует ручных шагов (см. runbook). Trade-off принят: дешевле чем платить за две VPS постоянно.
  - Latency Frankfurt → Telegram DC1 (~50 мс vs ~30 мс из РФ) — в пределах ТЗ KPI < 60 сек end-to-end.
  - Если в будущем потребуется prod в РФ ради ФЗ-152, инфраструктура раздвоится (prod в РФ + exit-нода вне).
- **Нейтральные.**
  - `cd-backend-dev.yml` SSH-target меняется через `gh secret set DEV_VPS_HOST=95.81.94.83 DEV_VPS_USER=user1` — без изменения yml.
  - Runbook `wireguard-split-tunnel.md` фигурирует в `docs/runbook/README.md` как «backup-/prod-only»; обновлять при следующей активации.
  - `CLAUDE.md` «Текущий статус» и «Среды» обновляются под новый host.

## Ссылки

- ТЗ разд. 4 (архитектура deploy), разд. 8 (Telegram anti-spam), разд. 9 (data residency).
- [ADR-0003](./0003-telethon-user-session-not-bot-api.md) — user-session vs Bot API, обоснование владения session-файлом.
- [docs/runbook/wireguard-split-tunnel.md](../runbook/wireguard-split-tunnel.md) — сохранён как deferred procedure.
- PR #59 (`3a3468c`) — FEATURE-03 Phase 1 listener, который и потребовал доступа к Telegram во время smoke 2026-05-12 на Frankfurt VPS.
