# ADR-0010: Dev VPS перенесён на FastVPS `5.188.20.39` (Ubuntu 26.04)

- **Статус:** Accepted
- **Дата:** 2026-07-20
- **Авторы:** Максим Ерохин
- **Заменяет:** [ADR-0009](./0009-dev-vps-frankfurt.md) (Frankfurt FirstByte `95.81.94.83`)

## Контекст

После ~2 месяцев простоя проекта (2026-05-12 … 2026-07-20) Frankfurt-бокс `user1@95.81.94.83` (FirstByte, ADR-0009) **стал недоступен по SSH** (`Connection timed out` на порту 22) — вероятно приостановлен/выключен провайдером за неоплату или простой. Восстанавливать старый бокс смысла нет: дешёвый dev-инстанс, состояние на нём не критично (session-файл всё равно перегенерируется).

Требования к замене те же, что в ADR-0009: прямой доступ к `api.telegram.org` (без WireGuard-обвязки), Docker + Compose, дешёвый dev-класс.

## Решение

**Dev VPS бэкенда — `user1@5.188.20.39` (FastVPS, hostname `sc5861fb8.fastvps-server.com`, Ubuntu 26.04 LTS, 1 vCPU / 2 GB RAM / 20 GB).**

Реактивная замена: старый бокс мёртв → поднят новый. Прямой доступ к Telegram подтверждён эмпирически — bootstrap Telethon-сессии и `backend-listener` подключились к Telegram без посредника.

### Bring-up (выполнен 2026-07-20)

- **`user1`** создан (`sudo` passwordless + группа `docker`), deploy-ключ `telegram_agregator_deploy_ed25519` установлен в `~/.ssh/authorized_keys` (700/600, `user1:user1`).
- **Docker Engine 29.6 + Compose v5.3** через официальный `get.docker.com` (apt-репозиторий Docker ещё не имеет codename `resolute`/26.04 — convenience-скрипт разрулил).
- Репозиторий склонирован в **`/home/user1/telegram-aggregator`** (совпадает с хардкодом пути в `cd-backend-{dev,prod}.yml` — правок workflow не потребовалось).
- **SSH захардненен** (drop-in `00-tla-hardening.conf` + правка main `sshd_config` + нейтрализация `50-cloud-init.conf`): `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `PermitRootLogin prohibit-password`, `PubkeyAuthentication yes`. Верифицировано `sshd -T`, не «reload прошёл».
- **GH Secrets** синхронизированы: `DEV_VPS_HOST=5.188.20.39` (`DEV_VPS_USER=user1`, `DEV_SSH_KEY` не менялись), свежий `TELETHON_SESSION_KEY` (Fernet). Прежний secret-drift закрыт.

## Последствия

- **Плюс:** `cd-backend-{dev,prod}.yml` не менялись — путь `/home/user1/telegram-aggregator` и `DEV_VPS_USER=user1` сохранены (минимальная замена по ADR-стратегии из 0009 §consequences).
- **Плюс:** SSH только по ключу — утёкший при настройке root-пароль для SSH бесполезен. Остаётся сменить root-пароль вручную (нужен для консоли провайдера).
- **Риск:** 1 vCPU / 2 GB — тесно для pg+redis+4 backend-сервиса; для dev приемлемо (как и прежний FirstByte KVM-SSD-1). При OOM/нагрузке — апгрейд тарифа.
- **Риск:** Ubuntu 26.04 bleeding-edge — часть apt-репозиториев (Docker) ещё без codename; используем convenience-скрипты/fallback.
- **2FA:** service-аккаунт `+375291953533` имеет включённый cloud password (см. [security.md](../security.md)) — bootstrap интерактивен и требует его ввода.

## Гео-локация

Точная локация FastVPS-инстанса не зафиксирована; ключевой операционный факт — **Telegram доступен напрямую** (проверено bootstrap'ом). Если понадобится жёсткий GDPR-периметр для PII лидов (ТЗ разд. 9) — уточнить датацентр у FastVPS отдельно.

## Ссылки

- Заменяет [ADR-0009](./0009-dev-vps-frankfurt.md).
- Runbook WireGuard split-tunnel — [`wireguard-split-tunnel.md`](../runbook/wireguard-split-tunnel.md) (не активирован; актуален только для сценария dev-в-РФ).
