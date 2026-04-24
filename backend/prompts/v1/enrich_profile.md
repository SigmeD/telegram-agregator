# enrich_profile — v1 (stub)

Промпт для LLM-обогащения профиля автора (см. TZ FEATURE-07).

Финальный текст будет добавлен одновременно с реализацией
`worker.tasks.enrich_profile`. План полей:

- Входные переменные: `bio`, `username`, `full_name`, `recent_messages`
  (последние 50 сообщений автора), `common_chats`.
- Выход (строгий JSON):
  - `role`: `founder` | `developer` | `investor` | `other` | `unknown`
  - `company_name`: string | null
  - `company_stage`: `idea` | `pre_mvp` | `mvp` | `growth` | `unknown`
  - `stack`: string[] (tech-stack keywords из bio/сообщений)
  - `external_links`: { `linkedin?`: url, `website?`: url, `twitter?`: url }
  - `is_founder_profile`: boolean
  - `reasoning`: string
