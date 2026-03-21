"""Humane Demo — the hook. Shows the full system working in 10 seconds."""

import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from humane.core.config import HumaneConfig, load_config
from humane.core.models import (
    ProposedAction, EntityType, ImpulseType, Verdict,
)
from humane.conductor import Conductor


def run_demo():
    console = Console()

    console.print()
    header = Text()
    header.append("══════════════════════════════════════════\n", style="yellow")
    header.append("  HUMANE DEMO", style="bold white")
    header.append("    live gate stack evaluation\n", style="dim")
    header.append("══════════════════════════════════════════", style="yellow")
    console.print(Panel(header, border_style="yellow", padding=(1, 2)))

    config_dir = Path.home() / ".humane"
    config_path = None
    if config_dir.exists():
        yamls = list(config_dir.glob("*.yaml"))
        if yamls:
            config_path = str(yamls[0])

    if config_path:
        config = load_config(config_path)
    else:
        config = HumaneConfig()
        config.db_path = str(config_dir / "demo.db")
        config_dir.mkdir(parents=True, exist_ok=True)

    conductor = Conductor(config=config, db_path=config.db_path)

    console.print("\n[dim]Loading demo context...[/] (3 synthetic entities, 2 goals, 1 week of history)")
    time.sleep(0.5)

    _seed_demo_data(conductor)

    state = conductor.human_state
    console.print(f"\n[yellow]◆[/]  [bold]HumanState initialized[/]")
    _print_state_bar(console, state)

    console.print(f"\n[dim]Simulating 6 hours of idle time...[/]")

    steps = [
        (0.08, 0.3),
        (0.43, 0.6),
        (0.71, 0.9),
    ]

    for boredom_val, progress in steps:
        time.sleep(0.8)
        state.boredom = boredom_val
        threshold_marker = " [yellow](threshold reached)[/]" if boredom_val >= config.boredom_trigger_threshold else ""
        console.print(f"   boredom climbing  [bold]{boredom_val:.2f}[/]{threshold_marker}")

    state.energy = max(0.4, state.energy - 0.3)
    state.fatigue = min(0.5, state.fatigue + 0.2)

    time.sleep(0.5)
    console.print(f"\n[yellow bold]⚡  IMPULSE FIRED[/]   [bold][IDLE_DISCOVERY][/]")
    console.print(f"   [dim]boredom drove unsolicited exploration[/]")

    discovery = ProposedAction(
        action_type="send_followup",
        payload={
            "discovery": "Proposal to Arjun @ DesignStudio — sent 11 days ago, no response logged.",
            "relationship": "Stable",
            "suggested_action": "gentle follow-up",
            "target": "arjun@designstudio.com",
        },
        confidence=0.61,
        rationale="Discovered unresolved open loop from 11 days ago during idle exploration",
        source="impulse",
        target_entity="arjun",
    )

    console.print()
    console.print(f'   discovery: [italic]"Proposal to Arjun @ DesignStudio — sent 11 days ago,[/]')
    console.print(f'   [italic]no response logged. Relationship: Stable. Suggested: gentle follow-up."[/]')

    time.sleep(1.0)
    console.print(f"\n[dim]Evaluating through gate stack...[/]")

    result = conductor.evaluate(discovery)

    time.sleep(0.3)
    for gr in result.gate_results:
        icon = "[green]✓[/]" if gr.verdict == Verdict.PROCEED else "[yellow]⚠[/]" if gr.verdict == Verdict.HOLD else "[red]✗[/]"
        engine_name = gr.engine.replace("_", " ").title()

        if gr.verdict == Verdict.HOLD:
            console.print(f"   {icon}  {engine_name:20s} —  [yellow]HOLD[/]  {gr.reason}")
        else:
            score_str = f"{gr.score:.2f}" if gr.score > 0 else ""
            detail = f"({score_str})" if score_str else ""
            console.print(f"   {icon}  {engine_name:20s} —  {detail} {gr.reason}")
        time.sleep(0.3)

    console.print()
    if result.final_verdict == Verdict.PROCEED:
        console.print("[green bold]→  Action APPROVED — executing.[/]")
    elif result.final_verdict == Verdict.HOLD:
        console.print("[yellow]→  Action queued for your review.[/]")
    else:
        console.print("[blue]→  Action deferred — will retry when state improves.[/]")

    console.print()
    console.print("────────────────────────────────────────", style="yellow")
    console.print("[bold]Your agent just noticed something you forgot about.[/]")
    console.print("[bold]Nobody asked it to. That's Humane.[/]")
    console.print("────────────────────────────────────────", style="yellow")
    console.print()
    console.print("[yellow]→[/]  run [bold]'humane'[/] to open the dashboard")
    console.print("[yellow]→[/]  run [bold]'humane status'[/] to check agent state")


def _seed_demo_data(conductor: Conductor):
    conductor.relational.add_entity("arjun", EntityType.PROSPECT)
    conductor.relational.add_entity("priya", EntityType.CLIENT)
    conductor.relational.add_entity("rahul", EntityType.CLOSE_COLLEAGUE)

    conductor.relational.log_interaction("arjun", 0.3, "Sent proposal for design work")
    conductor.relational.log_interaction("priya", 0.7, "Positive project kickoff call")
    conductor.relational.log_interaction("rahul", 0.5, "Regular sync, no issues")

    conductor.goal_engine.register_goal("Close DesignStudio deal", expected_value=0.8, milestones_total=5)
    conductor.goal_engine.register_goal("Launch Q2 marketing campaign", expected_value=0.6, milestones_total=8)

    conductor.memory_decay.add_memory(
        memory_type=__import__("humane.core.models", fromlist=["MemoryType"]).MemoryType.EPISODIC,
        content="Sent proposal to Arjun at DesignStudio, awaiting response",
    )


def _print_state_bar(console: Console, state):
    dims = [
        ("energy", state.energy, "yellow"),
        ("mood", state.mood, "green" if state.mood >= 0 else "red"),
        ("fatigue", state.fatigue, "red"),
        ("boredom", state.boredom, "yellow"),
    ]
    parts = []
    for name, val, color in dims:
        if name == "mood":
            parts.append(f"   {name} [bold]{val:+.2f}[/]")
        else:
            parts.append(f"   {name} [bold]{val:.2f}[/]")
    console.print("  ".join(parts))
