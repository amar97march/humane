"""HumanClaw TUI Dashboard — Industrial Utilitarian aesthetic.

Amber state bars, ASCII box-drawing, stark monochrome with gold accents.
"""

import time
from pathlib import Path

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align

from humanclaw.core.config import HumanClawConfig, load_config
from humanclaw.conductor import Conductor
from humanclaw.core.models import Verdict


AMBER = "color(214)"
DIM = "dim"
BOLD_WHITE = "bold white"
RED = "bold red"
GREEN = "bold green"


def _state_bar(value: float, width: int = 24, bidirectional: bool = False) -> Text:
    text = Text()
    if bidirectional:
        mid = width // 2
        if value >= 0:
            filled = int(value * mid)
            text.append("░" * mid, style="dim white")
            text.append("█" * filled, style=GREEN)
            text.append("░" * (mid - filled), style="dim white")
        else:
            filled = int(abs(value) * mid)
            text.append("░" * (mid - filled), style="dim white")
            text.append("█" * filled, style=RED)
            text.append("░" * mid, style="dim white")
    else:
        filled = int(value * width)
        text.append("█" * filled, style=AMBER)
        text.append("░" * (width - filled), style="dim white")
    return text


def _build_state_panel(conductor: Conductor) -> Panel:
    state = conductor.human_state
    table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    table.add_column("Dim", style=DIM, width=14)
    table.add_column("Val", style=BOLD_WHITE, width=7)
    table.add_column("Bar", width=26)

    dims = [
        ("ENERGY", state.energy, False),
        ("MOOD", state.mood, True),
        ("FATIGUE", state.fatigue, False),
        ("BOREDOM", state.boredom, False),
        ("SOCIAL_LOAD", state.social_load, False),
        ("FOCUS", state.focus, False),
    ]

    for name, val, bidir in dims:
        val_str = f"{val:+.2f}" if bidir else f"{val:.2f}"
        bar = _state_bar(val, bidirectional=bidir)
        table.add_row(name, val_str, bar)

    dqm = state.decision_quality_multiplier
    pref = state.preferred_task_type.value
    table.add_row("", "", "")
    table.add_row("DQ_MULT", f"{dqm:.2f}", Text(f"preferred: {pref}", style=DIM))

    return Panel(table, title="[bold]HUMANSTATE[/]", border_style=AMBER, padding=(0, 1))


def _build_queue_panel(conductor: Conductor) -> Panel:
    queue = conductor.get_hold_queue()
    table = Table(show_header=True, box=None, padding=(0, 1), expand=True, header_style=AMBER)
    table.add_column("ID", width=10)
    table.add_column("Type", width=18)
    table.add_column("Source", width=14)
    table.add_column("Conf", width=6)
    table.add_column("Reason", ratio=1)

    if not queue:
        table.add_row("[dim]—[/]", "[dim]no pending actions[/]", "", "", "")
    else:
        for item in queue[:10]:
            style = RED if "HARD VALUE" in item.hold_reason else AMBER
            table.add_row(
                item.id[:8] + "…",
                item.action.action_type,
                item.hold_source,
                f"{item.adjusted_confidence:.2f}",
                Text(item.hold_reason[:50], style=style),
            )

    footer = Text(f"  {len(queue)} pending  |  [a]pprove  [r]eject  [m]odify", style=DIM)
    content = Table.grid(expand=True)
    content.add_row(table)
    content.add_row(footer)
    return Panel(content, title="[bold]HOLD QUEUE[/]", border_style=AMBER, padding=(0, 1))


def _build_events_panel(conductor: Conductor) -> Panel:
    events = conductor.event_log.recent(limit=8)
    lines = Text()
    if not events:
        lines.append("  no events yet", style=DIM)
    else:
        for ev in reversed(events):
            ts = time.strftime("%H:%M:%S", time.localtime(ev["created_at"]))
            engine = ev.get("engine", "system")
            event_type = ev.get("event_type", "unknown")
            icon = "⚡" if "impulse" in event_type else "◆" if "proceed" in event_type else "⚠" if "held" in event_type else "·"
            lines.append(f"  {ts} ", style=DIM)
            lines.append(f"{icon} ", style=AMBER)
            lines.append(f"[{engine}] ", style="bold")
            lines.append(f"{event_type}\n", style="white")

    return Panel(lines, title="[bold]EVENT LOG[/]", border_style=AMBER, padding=(0, 1))


def _build_engines_panel(conductor: Conductor) -> Panel:
    engines = [
        ("1", "HumanState", "ACTIVE"),
        ("2", "Impulse", "ACTIVE"),
        ("3", "InactionGuard", "ACTIVE"),
        ("4", "Relational Memory", "ACTIVE"),
        ("5", "Dissent", "ACTIVE"),
        ("6", "Goal Abandon", "ACTIVE"),
        ("7", "Memory Decay", "ACTIVE"),
        ("8", "Social Risk", "ACTIVE"),
        ("9", "Anomaly Detector", "ACTIVE"),
        ("10", "Values Boundary", "ACTIVE"),
    ]
    table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    table.add_column("#", width=3, style=AMBER)
    table.add_column("Engine", width=20)
    table.add_column("Status", width=8)

    for num, name, status in engines:
        color = GREEN if status == "ACTIVE" else RED
        table.add_row(num, name, Text(status, style=color))

    return Panel(table, title="[bold]ENGINES[/]", border_style=AMBER, padding=(0, 1))


def _build_layout(conductor: Conductor) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )

    header_text = Text()
    header_text.append("  HUMANCLAW ", style="bold white on color(214)")
    header_text.append(f"  {conductor.config.agent_name}", style=DIM)
    header_text.append(f"  │  {time.strftime('%H:%M:%S')}", style=DIM)
    layout["header"].update(Panel(header_text, border_style=AMBER, padding=0))

    layout["body"].split_row(
        Layout(name="left", ratio=1),
        Layout(name="right", ratio=1),
    )

    layout["left"].split_column(
        Layout(_build_state_panel(conductor), name="state", ratio=2),
        Layout(_build_engines_panel(conductor), name="engines", ratio=2),
    )

    layout["right"].split_column(
        Layout(_build_queue_panel(conductor), name="queue", ratio=2),
        Layout(_build_events_panel(conductor), name="events", ratio=2),
    )

    footer = Text()
    footer.append("  hc › ", style=AMBER)
    footer.append("tab", style="bold")
    footer.append("/panels  ", style=DIM)
    footer.append("a", style="bold")
    footer.append("/approve  ", style=DIM)
    footer.append("r", style="bold")
    footer.append("/reject  ", style=DIM)
    footer.append("f", style="bold")
    footer.append("/fire impulse  ", style=DIM)
    footer.append("q", style="bold")
    footer.append("/quit", style=DIM)
    layout["footer"].update(Panel(footer, border_style=AMBER, padding=0))

    return layout


def run_dashboard():
    console = Console()

    config_dir = Path.home() / ".humanclaw"
    config_path = None
    if config_dir.exists():
        yamls = list(config_dir.glob("*.yaml"))
        if yamls:
            config_path = str(yamls[0])

    if config_path:
        config = load_config(config_path)
    else:
        config = HumanClawConfig()
        config.db_path = str(config_dir / "dashboard_demo.db")
        config_dir.mkdir(parents=True, exist_ok=True)

    conductor = Conductor(config=config, db_path=config.db_path)

    console.print(f"\n[{AMBER}]Starting HumanClaw dashboard...[/]")
    console.print(f"[{DIM}]Press Ctrl+C to exit[/]\n")

    try:
        with Live(_build_layout(conductor), console=console, refresh_per_second=1, screen=True) as live:
            while True:
                conductor.human_state.tick()
                result = conductor.tick()
                live.update(_build_layout(conductor))
                time.sleep(1)
    except KeyboardInterrupt:
        console.print(f"\n[{AMBER}]Dashboard closed.[/]")
