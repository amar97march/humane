"""Humane Init Wizard — 6 questions, under 90 seconds."""

import os
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.text import Text

from humane.core.config import HumaneConfig, save_config


def run_wizard():
    console = Console()

    header = Text()
    header.append("══════════════════════════════════════════\n", style="yellow")
    header.append("  HUMANE", style="bold white")
    header.append("    human behavioral middleware\n", style="dim")
    header.append("══════════════════════════════════════════", style="yellow")
    console.print(Panel(header, border_style="yellow", padding=(1, 2)))

    console.print("\n[bold]Let's set up your first agent. 6 questions.[/]\n")

    agent_name = Prompt.ask(
        "[yellow]?[/] Agent name [dim](used in dashboard and logs)[/]",
        default="humane-agent",
    )

    console.print("[dim]  Supported: anthropic (Claude), openai (GPT), gemini, groq, deepseek, ollama (local), custom[/]")
    llm_provider = Prompt.ask(
        "[yellow]?[/] LLM provider",
        choices=["anthropic", "openai", "gemini", "groq", "deepseek", "ollama", "custom"],
        default="anthropic",
    )

    model_defaults = {
        "anthropic": "claude-sonnet-4-20250514",
        "openai": "gpt-4o",
        "gemini": "gemini-2.0-flash",
        "groq": "llama-3.3-70b-versatile",
        "deepseek": "deepseek-chat",
        "ollama": "llama3",
        "custom": "",
    }
    llm_model = Prompt.ask(
        f"[yellow]?[/] Model [dim](default: {model_defaults.get(llm_provider, '')})[/]",
        default=model_defaults.get(llm_provider, ""),
    )

    if llm_provider == "ollama":
        api_key = ""
        console.print("[dim]  Ollama runs locally — no API key needed.[/]")
    else:
        api_key = Prompt.ask(
            "[yellow]?[/] API key [dim](saved to .env — not stored in config)[/]",
            password=True,
        )

    llm_base_url = ""
    if llm_provider == "custom":
        llm_base_url = Prompt.ask(
            "[yellow]?[/] Base URL [dim](OpenAI-compatible endpoint)[/]",
            default="",
        )

    active_hours = Prompt.ask(
        "[yellow]?[/] Active hours [dim](no impulses outside this window)[/]",
        default="7am – 10pm",
    )
    start_hour, end_hour = _parse_hours(active_hours)

    telegram_token = Prompt.ask(
        "[yellow]?[/] Telegram bot token [dim](from @BotFather — leave empty to skip)[/]",
        default="",
    )

    values_preset = Prompt.ask(
        "[yellow]?[/] Start with preset values?",
        choices=["business-safe", "open", "custom"],
        default="business-safe",
    )

    notification = "telegram" if telegram_token else "none"

    config = HumaneConfig(
        agent_name=agent_name,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
        active_hours_start=start_hour,
        active_hours_end=end_hour,
        notification_channel=notification,
        telegram_bot_token=telegram_token,
        values_preset=values_preset,
    )

    base_dir = Path.home() / ".humane"
    base_dir.mkdir(parents=True, exist_ok=True)

    config_path = base_dir / f"{agent_name}.yaml"
    config.db_path = str(base_dir / f"{agent_name}.db")
    save_config(config, str(config_path))

    env_path = base_dir / ".env"
    with open(env_path, "a") as f:
        key_var = f"HUMANE_{llm_provider.upper()}_API_KEY"
        f.write(f"{key_var}={api_key}\n")

    from humane.core.store import Store
    store = Store(config.db_path, encrypt_at_rest=config.encrypt_data_at_rest)
    store.initialize()

    if values_preset == "business-safe":
        _load_preset_values(store)

    console.print()
    console.print("══════════════════════════════════════════", style="yellow")
    console.print(f"[green]✓[/]  Config written     {config_path}")
    console.print(f"[green]✓[/]  Database created   {config.db_path}")
    console.print(f"[green]✓[/]  Values loaded      {values_preset} preset")
    if telegram_token:
        console.print(f"[green]✓[/]  Telegram bot       configured")
    console.print("══════════════════════════════════════════", style="yellow")
    console.print()
    console.print("[yellow]→[/]  run [bold]'humane serve'[/] to start bot + API + dashboard")
    console.print("[yellow]→[/]  run [bold]'humane demo'[/] to see the gate stack in action")


def _parse_hours(s: str) -> tuple[int, int]:
    s = s.lower().replace(" ", "").replace("–", "-").replace("—", "-")
    parts = s.split("-")
    if len(parts) != 2:
        return 7, 22

    def parse_h(h: str) -> int:
        h = h.strip()
        pm = "pm" in h
        am = "am" in h
        h = h.replace("am", "").replace("pm", "")
        try:
            val = int(h)
        except ValueError:
            return 7
        if pm and val < 12:
            val += 12
        if am and val == 12:
            val = 0
        return val

    return parse_h(parts[0]), parse_h(parts[1])


def _load_preset_values(store):
    import yaml
    preset_path = Path(__file__).parent.parent.parent / "presets" / "business_safe.yaml"
    if not preset_path.exists():
        return

    with open(preset_path) as f:
        data = yaml.safe_load(f)

    from humane.core.models import ValueStatement, ValueSeverity

    for v in data.get("values", []):
        stmt = ValueStatement(
            id=v["id"],
            description=v["description"],
            behavioral_pattern=v["behavioral_pattern"],
            violation_examples=v["violation_examples"],
            honoring_examples=v["honoring_examples"],
            severity=ValueSeverity.HARD if v["severity"] == "hard" else ValueSeverity.SOFT,
        )
        store.add_value(stmt)
