# Delivery with a systemd timer (example)

The plugin stores and shows reminders; to get due ones in Telegram something must run `remind.py tick` regularly.
This is one way, not part of the plugin. Adjust the paths to where the plugin lives (`claude plugin list` shows it)
and fill in the values.

`~/.config/systemd/user/remind.service`:

```ini
[Unit]
Description=Send overdue reminders to Telegram

[Service]
Type=oneshot
Environment=REMIND_PANE_TELEGRAM_TOKEN=<bot token>
Environment=REMIND_PANE_TELEGRAM_CHAT=<chat id>
Environment=REMIND_PANE_TZ=Europe/Berlin
ExecStart=/usr/bin/python3 -I /path/to/remind-pane/backend/remind.py tick
```

`~/.config/systemd/user/remind.timer`:

```ini
[Unit]
Description=Check reminders every minute

[Timer]
OnCalendar=*-*-* *:*:00
AccuracySec=1s
Unit=remind.service

[Install]
WantedBy=timers.target
```

```
chmod 600 ~/.config/systemd/user/remind.service   # it holds the token
systemctl --user daemon-reload
systemctl --user enable --now remind.timer
python3 /path/to/remind-pane/backend/remind.py test   # with the same variables exported
journalctl --user -u remind.service
```

Set `REMIND_PANE_DATA` too if the pane uses a non-default data folder. Cron works the same:
`* * * * * REMIND_PANE_TELEGRAM_TOKEN=… REMIND_PANE_TELEGRAM_CHAT=… python3 -I /path/to/remind.py tick`.
