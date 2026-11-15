# ansible-awg-gateway

Автоматизация частного удалённого доступа через два Ubuntu-сервера на базе
AmneziaWG 3.1. Исходники AWG собираются на серверах из закреплённых GitHub commit.
Лицензия — Apache 2.0.

```text
Устройства → jump → backbone → gateway → внешняя сеть
```

`jump` принимает подключения устройств с любых публичных IP. `gateway`
инициирует межсерверное UDP-соединение и обеспечивает выход во внешнюю сеть.
SSH обоих серверов сохраняет обычный публичный маршрут.

## Подготовка доступа

Нужны два выделенных Ubuntu-сервера, пользователь с sudo и известные имена
внешних интерфейсов. Проект управляет всем ruleset nftables; не используйте
параллельно другой менеджер firewall.

**SSH-ключи устанавливаются вручную до запуска Ansible.** Добавьте публичный
ключ в `~/.ssh/authorized_keys` нужного пользователя на каждом сервере через
консоль провайдера или существующий доступ:

```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub ADMIN_USER@JUMP_PUBLIC_IP
ssh-copy-id -i ~/.ssh/id_ed25519.pub ADMIN_USER@GATEWAY_PUBLIC_IP
```

Проверьте вход по ключу на оба сервера:

```bash
ssh -i ~/.ssh/id_ed25519 -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no ADMIN_USER@JUMP_PUBLIC_IP
ssh -i ~/.ssh/id_ed25519 -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no ADMIN_USER@GATEWAY_PUBLIC_IP
```

Замените адреса и пользователя своими значениями. Если подключаетесь как `root`,
ключ должен быть установлен для `root`. Playbook не меняет `authorized_keys`;
он отключает парольный вход и задаёт `PermitRootLogin prohibit-password`.

## Установка

На управляющей машине нужны Python с venv и SSH. Из корня проекта:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-controller.txt
ansible-galaxy collection install -r collections/requirements.yml
cp inventories/example.ini inventories/production.ini
```

Заполните `production.ini`: публичные IPv4, SSH-пользователя и внешний интерфейс
каждого узла. Подсети, порты, MTU и DNS задаются в `inventories/group_vars/all.yml`.
Проверьте, что адресация не пересекается с существующей сетью.

```bash
ansible-playbook playbooks/site.yml --syntax-check
ansible-playbook playbooks/site.yml --tags install
ansible-playbook playbooks/validate.yml
```

Для выбора приватного SSH-ключа используйте `--private-key /path/to/key` или
SSH-agent. При необходимости добавьте `--ask-become-pass` для sudo.

Порядок ролей: `prepare` → `firewall` → `network` → `awg` → `users`.
Тег `install` включает подготовку SSH и установку первых трёх основных ролей.
Отдельные теги: `ssh`, `firewall`, `network`, `awg`, `users`.
Полный повторный запуск — `ansible-playbook playbooks/site.yml`.

## Управление доступом устройств

```bash
ansible-playbook playbooks/clients.yml --tags client_add -e client_name=iphone
ansible-playbook playbooks/clients.yml --tags client_list
ansible-playbook playbooks/clients.yml --tags client_export -e client_name=iphone
ansible-playbook playbooks/clients.yml --tags client_remove -e client_name=iphone
```

Каждому устройству выдаются отдельные ключи и адрес. Повторное добавление
сохраняет существующие данные. Отзыв не затрагивает остальные подключения.

Файлы сохраняются локально в `local/clients/iphone/`:

- `iphone.conf` — профиль подключения;
- `iphone.png` — QR с профилем;
- `iphone.url` — ссылка подключения.

## Состояние и ограничения

- `local/state.json` содержит ключи и реестр устройств. Храните защищённую
  резервную копию `local/`; каталог исключён из Git.
- Приватные файлы имеют права `0600`, каталог состояния — `0700`.
- Не запускайте изменения одновременно с разных управляющих машин.
  Оставшуюся после аварии блокировку `local/.lock` удаляйте только после
  завершения всех процессов Ansible.
- Firewall применяется с проверкой синтаксиса и таймером отката при потере SSH.
- При отказе backbone клиентский трафик не должен уходить через внешний
  интерфейс `jump`: действуют запрещающий маршрут и правило firewall.
- Поддерживается IPv4. Обычный IPv6-доступ устройства сервером не блокируется.
- Изменение подсетей, имён интерфейсов или SSH-порта требует отдельной миграции.
- Полный режим `--check` пока не поддерживается.

## Проверки

```bash
ansible-playbook playbooks/validate.yml
ansible-playbook playbooks/validate.yml --tags udp
ansible-playbook playbooks/validate.yml --tags failover
ansible-playbook playbooks/validate.yml --tags reboot
```

`failover` временно останавливает backbone, `reboot` перезагружает узлы.
Оба режима прерывают подключения и запускаются только явным тегом.
`udp` показывает краткие заголовки без сохранения содержимого трафика.
Для проверки внешнего адреса используется api.ipify.org.

Локальные проверки пройдены. Развёртывание на двух серверах, восстановление
SSH и импорт профилей на целевых устройствах ещё требуют практической проверки.
