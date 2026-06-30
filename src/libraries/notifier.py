"""
Push notifications via ntfy.sh.

Topic : goblin-lab-r9k2mq
Subscribe: https://ntfy.sh/goblin-lab-r9k2mq
  - iOS/Android: install the ntfy app and subscribe to the topic
  - Browser: open the URL above
"""

import urllib.request

NTFY_TOPIC = "goblin-lab-r9k2mq"
_NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"


def notify(message: str, title: str = "autotomo", priority: str = "default") -> None:
    """
    Send a push notification. Silently swallows all errors so a network
    issue never interrupts or crashes a running experiment.
    """
    try:
        req = urllib.request.Request(
            _NTFY_URL,
            data=message.encode(),
            headers={
                "Title": title,
                "Priority": priority,
                "Tags": "microscope",
            },
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass
