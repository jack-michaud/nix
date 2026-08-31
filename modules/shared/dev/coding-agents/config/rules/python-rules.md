---
paths: ["**/*.py"]
---

# Python rules

How to write Python in this repo.

## Feedback log

### 2026-08-30 -- No inline imports

- **Rule:** all imports must be placed at the top level of the module; do not use inline imports inside functions or methods.
- **Example:**
  - bad (`jack-michaud/j0nk` at `6be30a3eb93ca806c4cf4b540e8a27e90d3ae57b`, `j0nk/__init__.py:57-67`):
    ```python
    def main():
        from dotenv import load_dotenv

        from .bot import Bot, run_bot

        load_dotenv()
        logging.config.dictConfig(LOGGING_CONFIG)

        bot = Bot(extensions=BOT_EXTENSIONS)
        run_bot(bot)
    ```
  - good (`jack-michaud/j0nk` at `c917f2565f18b22f9a1c678a05c398f960076ff2`, `j0nk/__init__.py:1-10,49-68`): top-level imports at the module level:
    ```python
    import logging.config
    import ollama
    import pythonjsonlogger
    from injector import Injector, singleton
    from .bot import Bot, run_bot

    from dotenv import load_dotenv


    load_dotenv()
    ```
- **Why:** Jack did not state a reason.
- (tuicr comment: b5ff4904-dc46-439f-bc17-a19991511dec)
