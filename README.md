# ansible-awg-gateway

## Архитектура

Проект использует два сервера (`jump` и `gateway`) и два независимых туннеля AmneziaWG 3.1: клиентский доступ и межсерверный канал.

```text
iPhone / Windows / Linux / Android / и тд
          |
          | AWG 3.1 (клиентский доступ)
          v
    ┌──────────────┐
    │ jump         │
    │              │
    │ awg-client   │
    │ awg-backbone │
    └──────┬───────┘
           ^
           | backbone: AWG 3.1
           | Инициатор — gateway
           |
    ┌──────┴───────┐
    │ gateway      │
    │              │
    │ NAT          │
    │ IP forwarding│
    └──────┬───────┘
           |
           v
      Внешняя сеть
```

### Компоненты

- **jump** — точка входа, принимающая подключения устройств с любых публичных IP.
- **awg-client** — интерфейс клиентского доступа на `jump`.
- **awg-backbone** — интерфейс межсерверного канала на `jump`.
- **backbone** — зашифрованный канал AWG 3.1 между `jump` и `gateway`.
- **gateway** — выходной шлюз, инициирующий межсерверное соединение и обеспечивающий NAT и IP forwarding.

### Принцип работы

1. Устройство подключается к `jump` через AWG 3.1.
2. `jump` направляет клиентский трафик через `backbone`.
3. Межсерверный канал инициируется со стороны `gateway`.
4. `gateway` обеспечивает выход во внешнюю сеть.
5. Ответный трафик возвращается по тому же маршруту.

После установления межсерверного соединения передача данных осуществляется в обоих направлениях.

## Требования

- Две выделенные VPS с публичными IPv4 и доступом по SSH-ключу.
- На серверах — Ubuntu 24.04 и пользователь `root` либо пользователь с sudo.
- На управляющем компьютере — Python 3, модуль `venv` и SSH-клиент.

Проект управляет всем набором правил nftables. Серверы не должны использовать
другой менеджер firewall. SSH-ключи необходимо установить самостоятельно:
проект отключает парольную аутентификацию, но не добавляет ключи доступа.

## Установка
В примерах используется вход на серверы от `root`.

### 1. Подготовка SSH-доступа

Установите публичный ключ и проверьте подключение к обоим серверам:

### 2. Подготовка управляющего окружения

Для управляющего компьютера на Ubuntu 24.04 системные зависимости устанавливаются так:

```bash
sudo apt update
sudo apt install python3 python3-venv openssh-client
```

Создайте окружение проекта и установите зависимости:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-controller.txt
ansible-galaxy collection install -r collections/requirements.yml
```

`requirements-controller.txt` устанавливает Ansible, библиотеку `cryptography`
для генерации ключей и `qrcode[pil]` для экспорта QR-кодов.
`collections/requirements.yml` содержит коллекции модулей, используемых ролями.

Окружение `.venv` изолирует эти зависимости от системных Python-пакетов.
Активация добавляет его команды в `PATH`, поэтому Ansible запускается обычной
командой `ansible-playbook`. В каждом новом терминале перед работой с проектом
достаточно выполнить `source .venv/bin/activate`; повторная установка не требуется.

### 3. Настройка inventory

Создайте `inventory.ini` в корне репозитория:

```ini
[jump]
jump-node ansible_host=JUMP_IP awg_external_interface=eth0

[gateway]
gateway-node ansible_host=GATEWAY_IP awg_external_interface=eth0

[all:vars]
ansible_user=root
ansible_ssh_private_key_file=/home/USER/.ssh/id_ed25519
```

Замените IP-адреса и путь к приватному ключу. Для каждого сервера укажите имя
внешнего интерфейса: в выводе `ip route show default` оно следует после `dev`.
Подсети, порты, MTU и DNS задаются в `group_vars/all.yml`.
Ansible автоматически читает `inventory.ini` через `ansible.cfg`.

Проверьте доступность серверов:

```bash
ansible all -m ping
```

### 4. Развёртывание и проверка

Выполните этапы последовательно. При ошибке устраните причину перед переходом
к следующей команде.

```bash
ansible-playbook playbooks/site.yml --tags ssh
ansible-playbook playbooks/site.yml --tags firewall
ansible-playbook playbooks/site.yml --tags network
ansible-playbook playbooks/site.yml --tags awg
ansible-playbook playbooks/validate.yml
```

Исходники AWG собираются непосредственно на VPS. Первая сборка может занять
несколько минут. Проверочный playbook проверяет службы, связь между узлами,
маршрутизацию и внешний IP выхода через `gateway`.

Все этапы установки также доступны одной командой:

```bash
ansible-playbook playbooks/site.yml --tags install
```

## Управление устройствами

Добавление устройства:

```bash
ansible-playbook playbooks/clients.yml --tags client_add -e client_name=iphone
```

Результат сохраняется в `local/clients/iphone/`:

| Файл | Назначение |
| --- | --- |
| `iphone.png` | QR-код для импорта в AmneziaWG |
| `iphone.conf` | Профиль подключения |
| `iphone.url` | Ссылка подключения |

Для каждого устройства используйте отдельное имя. Повторное добавление с тем же
именем сохраняет существующие ключи и адрес.

Просмотр списка, повторный экспорт и отзыв доступа:

```bash
ansible-playbook playbooks/clients.yml --tags client_list
ansible-playbook playbooks/clients.yml --tags client_export -e client_name=iphone
ansible-playbook playbooks/clients.yml --tags client_remove -e client_name=iphone
```

Каталог `local/` содержит приватные ключи и реестр устройств: храните его резервную
копию в защищённом месте. `local/` и `inventory.ini` исключены из Git.

## Лицензия

[Apache License 2.0](LICENSE).
