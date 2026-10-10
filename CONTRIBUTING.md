# Contributing

Bug reports, ideas and pull requests are welcome.

- **Bug** — open an [issue](https://github.com/34823/remind-pane/issues/new/choose) with the error text from the pane, OS, Python and Claude Code versions.
- **Idea or question** — [Discussions](https://github.com/34823/remind-pane/discussions).
- **Pull request** — keep it small and focused; before sending run:

```
claude plugin validate . --strict
claude plugin test .
python3 -m unittest discover tests
```

Do not put your `reminders.json`, bot tokens or chat ids into issues or commits.
