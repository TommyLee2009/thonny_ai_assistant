# Contributing

## Development environment

Use the Python interpreter bundled with a supported Thonny installation:

```powershell
& "C:\Program Files\Thonny\python.exe" -m pip install -e .
& "C:\Program Files\Thonny\python.exe" -m unittest discover -s tests -v
```

## Pull requests

- Keep provider protocol changes compatible with the OpenAI Chat Completions
  API.
- Add or update tests for localization, request construction, and
  configuration behavior.
- Do not include API keys, local configuration files, student data, or
  screenshots containing credentials.
- Preserve the upstream copyright and MIT license notice.

## Reporting issues

Include the Thonny version, Python version, operating system, and a redacted
error message. Never post a real API key in a public issue.
