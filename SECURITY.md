# Security Policy

## Supported versions

Security fixes are provided for the latest published version of
`thonny-ai-assistant`.

## Reporting a vulnerability

Please report security issues privately to:

**TommyLee2009**  
Email: [lcy28898830@gmail.com](mailto:lcy28898830@gmail.com)

Do not include real API keys, student records, or other sensitive data in a
public GitHub issue. If a credential has been exposed, revoke it at the
provider immediately and create a replacement.

## Local data

The plugin stores provider configuration and chat history in:

```text
~/.thonny/thonny_ai_assistant_config/config.json
```

API keys are stored as plain text in this local file. The file is created with
user-only permissions where the operating system supports POSIX modes. Users
must protect it and must not commit it to GitHub.
